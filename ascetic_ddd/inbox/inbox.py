"""Inbox pattern implementation."""

import asyncio
import json
import typing
from typing import AsyncIterator, Callable, Awaitable
from abc import abstractmethod
from collections import defaultdict
from typing import Any

from ascetic_ddd.inbox.interfaces import IInbox, ISubscriber
from ascetic_ddd.inbox.message import InboxMessage
from ascetic_ddd.seedwork.domain.session.interfaces import ISessionPool
from ascetic_ddd.seedwork.infrastructure.session.interfaces import IPgSession


__all__ = (
    'Inbox',
)


class Inbox(IInbox):
    """Inbox pattern implementation using PostgreSQL.

    Ensures idempotency and causal consistency for incoming integration messages.
    """

    _table: str = 'inbox'
    _sequence: str = 'inbox_received_position_seq'
    _subscribers: dict[tuple[str, int], list[ISubscriber]]

    def __init__(self, session_pool: ISessionPool):
        """Initialize Inbox.

        Args:
            session_pool: Pool for obtaining database sessions.
        """
        self._session_pool = session_pool
        self._subscribers = defaultdict(list)

    def subscribe(
            self,
            event_type: str,  # topic_name?
            event_version: int,
            handler: typing.Optional[ISubscriber] = None
    ) -> Callable[[ISubscriber], ISubscriber] | None:

        def deco(func: ISubscriber) -> ISubscriber:
            self._subscribers[(event_type, event_version)].append(func)
            return func

        if handler is not None:
            deco(handler)
            return None
        else:
            return deco

    async def publish(self, message: InboxMessage) -> None:
        """Receive and store an incoming message.

        Uses INSERT ... ON CONFLICT DO NOTHING for idempotency.
        """
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._insert_message(session, message)

    async def handle(self) -> bool:
        """Process the next unprocessed message with satisfied dependencies."""
        async with self._session_pool.session() as session:
            async with session.atomic():
                message = await self._fetch_next_processable(session)
                if message is None:
                    return False

                await self.do_handle(session, message)
                await self._mark_processed(session, message)
                return True

    @abstractmethod
    async def do_handle(self, session: IPgSession, message: InboxMessage) -> None:
        """Process a single message. Override in subclasses."""
        key = (message.event_type, message.event_version)
        if key in self._subscribers:
            for handler in self._subscribers[key]:
                await handler(session, message)
        else:
            # Just watch for a message, mark it as processed.
            pass

    def __aiter__(self) -> AsyncIterator[tuple[IPgSession, InboxMessage]]:
        """Return async iterator for continuous message processing.

        Usage:
            async for session, message in inbox:
                # Process message within transaction
                await handle_message(session, message)
                # Message is automatically marked as processed after yield

        The iterator runs indefinitely, polling for new messages.
        Use Ctrl+C or break to stop.
        """
        return self._iterate()

    async def _iterate(
            self, poll_interval: float = 1.0
    ) -> AsyncIterator[tuple[IPgSession, InboxMessage]]:
        """Async generator that yields (session, message) pairs.

        Args:
            poll_interval: Seconds to wait when no messages available.

        Yields:
            Tuple of (session, message) for each processable message.
            Message is marked as processed after the yield returns.
        """
        while True:
            async with self._session_pool.session() as session:
                async with session.atomic():
                    message = await self._fetch_next_processable(session)

                    if message is None:
                        # No processable messages, wait before polling again
                        await asyncio.sleep(poll_interval)
                        continue

                    # Yield to caller for processing, mark as processed after
                    try:
                        yield session, message
                    finally:
                        await self._mark_processed(session, message)

    async def run(
            self,
            workers: int = 1,
            poll_interval: float = 1.0
    ) -> None:
        """Run message processing with concurrent workers.

        Args:
            workers: Number of concurrent workers.
            poll_interval: Seconds to wait when no messages available.
        """
        if workers == 1:
            await self._worker(poll_interval)
        else:
            tasks = [
                asyncio.create_task(self._worker(poll_interval))
                for _ in range(workers)
            ]
            await asyncio.gather(*tasks)

    async def _worker(self, poll_interval: float = 1.0) -> None:
        """Single worker loop for processing messages."""
        while True:
            processed = await self.handle()
            if not processed:
                await asyncio.sleep(poll_interval)

    async def _insert_message(self, session: IPgSession, message: InboxMessage) -> None:
        """Insert message into inbox table."""
        sql = """
            INSERT INTO %s (
                tenant_id, stream_type, stream_id, stream_position,
                event_type, event_version, payload, metadata
            ) VALUES (
                %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s
            )
            ON CONFLICT (tenant_id, stream_type, stream_id, stream_position) DO NOTHING
        """ % self._table

        async with session.connection.cursor() as cursor:
            await cursor.execute(
                sql,
                (
                    message.tenant_id,
                    message.stream_type,
                    json.dumps(message.stream_id),
                    message.stream_position,
                    message.event_type,
                    message.event_version,
                    json.dumps(message.payload),
                    json.dumps(message.metadata) if message.metadata else None,
                )
            )

    async def _fetch_next_processable(
            self, session: IPgSession, start_offset: int = 0
    ) -> InboxMessage | None:
        """Find next message with satisfied dependencies.

        Args:
            session: Database session.
            start_offset: Offset to start searching from.

        Returns:
            Next processable message or None if no messages available.
        """
        offset = start_offset
        while True:
            message = await self._fetch_unprocessed_message(session, offset)
            if message is None:
                return None
            if await self._are_dependencies_satisfied(session, message):
                return message
            offset += 1

    async def _fetch_unprocessed_message(
            self, session: IPgSession, offset: int
    ) -> InboxMessage | None:
        """Fetch first unprocessed message at given offset with row-level lock."""
        sql = """
            SELECT
                tenant_id, stream_type, stream_id, stream_position,
                event_type, event_version, payload, metadata,
                received_position, processed_position
            FROM %s
            WHERE processed_position IS NULL
            ORDER BY received_position ASC
            LIMIT 1 OFFSET %%s
            FOR UPDATE SKIP LOCKED
        """ % self._table

        async with session.connection.cursor() as cursor:
            await cursor.execute(sql, (offset,))
            row = await cursor.fetchone()

        if row is None:
            return None

        return InboxMessage(
            tenant_id=row[0],
            stream_type=row[1],
            stream_id=row[2] if isinstance(row[2], dict) else json.loads(row[2]),
            stream_position=row[3],
            event_type=row[4],
            event_version=row[5],
            payload=row[6] if isinstance(row[6], dict) else json.loads(row[6]),
            metadata=row[7] if row[7] is None or isinstance(row[7], dict) else json.loads(row[7]),
            received_position=row[8],
            processed_position=row[9],
        )

    async def _are_dependencies_satisfied(
            self, session: IPgSession, message: InboxMessage
    ) -> bool:
        """Check if all causal dependencies are processed."""
        dependencies = message.causal_dependencies
        if not dependencies:
            return True

        for dep in dependencies:
            if not await self._is_dependency_processed(session, dep):
                return False

        return True

    async def _is_dependency_processed(
            self, session: IPgSession, dependency: dict[str, Any]
    ) -> bool:
        """Check if a single dependency is processed."""
        sql = """
            SELECT 1 FROM %s
            WHERE tenant_id = %%s
              AND stream_type = %%s
              AND stream_id = %%s
              AND stream_position = %%s
              AND processed_position IS NOT NULL
            LIMIT 1
        """ % self._table

        async with session.connection.cursor() as cursor:
            await cursor.execute(
                sql,
                (
                    dependency['tenant_id'],
                    dependency['stream_type'],
                    json.dumps(dependency['stream_id']),
                    dependency['stream_position'],
                )
            )
            row = await cursor.fetchone()

        return row is not None

    async def _mark_processed(self, session: IPgSession, message: InboxMessage) -> None:
        """Mark message as processed with next sequence value."""
        sql = """
            UPDATE %s
            SET processed_position = nextval('%s')
            WHERE tenant_id = %%s
              AND stream_type = %%s
              AND stream_id = %%s
              AND stream_position = %%s
        """ % (self._table, self._sequence)

        async with session.connection.cursor() as cursor:
            await cursor.execute(
                sql,
                (
                    message.tenant_id,
                    message.stream_type,
                    json.dumps(message.stream_id),
                    message.stream_position,
                )
            )

    async def setup(self) -> None:
        """Create inbox table and sequence if they don't exist."""
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._create_sequence(session)
                await self._create_table(session)

    async def _create_sequence(self, session: IPgSession) -> None:
        """Create sequence for received_position."""
        sql = "CREATE SEQUENCE IF NOT EXISTS %s" % self._sequence
        async with session.connection.cursor() as cursor:
            await cursor.execute(sql)

    async def _create_table(self, session: IPgSession) -> None:
        """Create inbox table."""
        sql = """
            CREATE TABLE IF NOT EXISTS %s (
                tenant_id varchar(128) NOT NULL,
                stream_type varchar(128) NOT NULL,
                stream_id jsonb NOT NULL,
                stream_position integer NOT NULL,
                event_type varchar(60) NOT NULL,
                event_version smallint NOT NULL,
                payload jsonb NOT NULL,
                metadata jsonb NULL,
                received_position bigint NOT NULL UNIQUE DEFAULT nextval('%s'),
                processed_position bigint NULL,
                CONSTRAINT %s_pk PRIMARY KEY (tenant_id, stream_type, stream_id, stream_position)
            )
        """ % (self._table, self._sequence, self._table)
        async with session.connection.cursor() as cursor:
            await cursor.execute(sql)

    async def cleanup(self) -> None:
        """Cleanup resources (no-op for now)."""
        pass
