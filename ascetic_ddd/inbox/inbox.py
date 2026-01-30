"""Inbox pattern implementation."""

import json
import typing
from typing import Callable, Awaitable
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
        return await self._handle_with_offset(0)

    @abstractmethod
    async def do_handle(self, session: IPgSession, message: InboxMessage) -> None:
        """Process a single message. Override in subclasses."""
        key = (message.event_type, message.event_version)
        if key in self._subscribers:
            for handler in self._subscribers[key]:
                handler(session, message)
        else:
            # Just watch for a message, mark it as processed.
            pass

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

    async def _handle_with_offset(self, offset: int) -> bool:
        """Process message at given offset, recursively trying next if dependencies not met."""
        async with self._session_pool.session() as session:
            async with session.atomic():
                message = await self._fetch_unprocessed_message(session, offset)
                if message is None:
                    return False

                if not await self._are_dependencies_satisfied(session, message):
                    # Try next message recursively
                    return await self._handle_with_offset(offset + 1)

                # Process the message
                await self.do_handle(session, message)

                # Mark as processed
                await self._mark_processed(session, message)
                return True

    async def _fetch_unprocessed_message(
            self, session: IPgSession, offset: int
    ) -> InboxMessage | None:
        """Fetch first unprocessed message at given offset."""
        sql = """
            SELECT
                tenant_id, stream_type, stream_id, stream_position,
                event_type, event_version, payload, metadata,
                received_position, processed_position
            FROM %s
            WHERE processed_position IS NULL
            ORDER BY received_position ASC
            LIMIT 1 OFFSET %%s
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
