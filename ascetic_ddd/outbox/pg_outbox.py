"""PostgreSQL implementation of the Transactional Outbox pattern."""

import asyncio
import typing

from psycopg.types.json import Jsonb

from ascetic_ddd.outbox.interfaces import IOutbox, IOutboxPublisher
from ascetic_ddd.outbox.message import OutboxMessage
from ascetic_ddd.seedwork.domain.session.interfaces import ISessionPool
from ascetic_ddd.seedwork.infrastructure.session.interfaces import IPgSession


__all__ = ('PgOutbox',)


class PgOutbox(IOutbox):
    """PostgreSQL implementation of the Transactional Outbox pattern.

    Uses transaction_id (xid8) for correct ordering across concurrent transactions.
    See init.sql for schema and detailed documentation.
    """

    _session_pool: ISessionPool
    _outbox_table: str
    _offsets_table: str
    _batch_size: int

    def __init__(
            self,
            session_pool: ISessionPool,
            outbox_table: str = 'outbox',
            offsets_table: str = 'outbox_offsets',
            batch_size: int = 100
    ):
        self._session_pool = session_pool
        self._outbox_table = outbox_table
        self._offsets_table = offsets_table
        self._batch_size = batch_size

    async def publish(
            self,
            session: 'IPgSession',
            message: 'OutboxMessage'
    ) -> None:
        """Store a message in the outbox within the current transaction."""
        sql = """
            INSERT INTO %s (event_type, event_version, payload, metadata, transaction_id)
            VALUES (%%(event_type)s, %%(event_version)s, %%(payload)s, %%(metadata)s, pg_current_xact_id())
        """ % (self._outbox_table,)

        params = {
            'event_type': message.event_type,
            'event_version': message.event_version,
            'payload': self._to_jsonb(message.payload),
            'metadata': self._to_jsonb(message.metadata),
        }

        async with session.connection.cursor() as cursor:
            await cursor.execute(sql, params)

    async def dispatch(
            self,
            publisher: 'IOutboxPublisher',
            consumer_group: str = ''
    ) -> bool:
        """Dispatch the next batch of unprocessed messages."""
        async with self._session_pool.session() as session:
            await self._ensure_consumer_group(session, consumer_group)

        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                # FOR UPDATE blocks if another dispatcher holds the lock
                messages = await self._fetch_messages(tx_session, consumer_group)

                if not messages:
                    return False

                # Publish each message
                for message in messages:
                    await publisher(message)

                # Update consumer position to the last message
                last = messages[-1]
                await self._ack_message(tx_session, consumer_group, last.transaction_id, last.position)

                return True

    def __aiter__(self) -> typing.AsyncIterator['OutboxMessage']:
        """Return async iterator for continuous message dispatching."""
        return self._message_iterator()

    async def _message_iterator(
            self,
            consumer_group: str = '',
            poll_interval: float = 1.0
    ) -> typing.AsyncGenerator['OutboxMessage', None]:
        """Async generator that yields messages continuously."""
        # Ensure consumer group exists (once, before loop)
        async with self._session_pool.session() as session:
            await self._ensure_consumer_group(session, consumer_group)

        while True:
            messages: list[OutboxMessage] = []

            async with self._session_pool.session() as session:
                async with session.atomic() as tx_session:
                    messages = await self._fetch_messages(tx_session, consumer_group)

                    for message in messages:
                        yield message
                        # Ack after each message is processed
                        await self._ack_message(
                            tx_session, consumer_group,
                            message.transaction_id, message.position
                        )

            if not messages:
                await asyncio.sleep(poll_interval)

    async def run(
            self,
            publisher: 'IOutboxPublisher',
            consumer_group: str = '',
            workers: int = 1,
            poll_interval: float = 1.0
    ) -> None:
        """Run message dispatching with concurrent workers."""
        async def worker():
            while True:
                has_messages = await self.dispatch(publisher, consumer_group)
                if not has_messages:
                    await asyncio.sleep(poll_interval)

        tasks = [asyncio.create_task(worker()) for _ in range(workers)]
        await asyncio.gather(*tasks)

    async def setup(self) -> None:
        """Initialize the outbox (create tables, sequences, indexes)."""
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                await self._create_outbox_table(tx_session)
                await self._create_offsets_table(tx_session)

    async def _create_outbox_table(self, session: 'IPgSession') -> None:
        """Create outbox table with indexes."""
        sql = """
            CREATE TABLE IF NOT EXISTS %s (
                "position" BIGSERIAL,
                "event_type" VARCHAR(255) NOT NULL,
                "event_version" SMALLINT NOT NULL DEFAULT 1,
                "payload" JSONB NOT NULL,
                "metadata" JSONB NOT NULL,
                "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                "transaction_id" xid8 NOT NULL,
                PRIMARY KEY ("transaction_id", "position")
            )
        """ % (self._outbox_table,)
        async with session.connection.cursor() as cursor:
            await cursor.execute(sql)

        # Index for position-based queries
        sql = """
            CREATE INDEX IF NOT EXISTS %s_position_idx ON %s ("position")
        """ % (self._outbox_table, self._outbox_table)
        async with session.connection.cursor() as cursor:
            await cursor.execute(sql)

        # Index for event_type filtering
        sql = """
            CREATE INDEX IF NOT EXISTS %s_event_type_idx ON %s ("event_type")
        """ % (self._outbox_table, self._outbox_table)
        async with session.connection.cursor() as cursor:
            await cursor.execute(sql)

        # Unique index on event_id for idempotency
        sql = """
            CREATE UNIQUE INDEX IF NOT EXISTS %s_event_id_uniq
            ON %s (((metadata->>'event_id')::uuid))
        """ % (self._outbox_table, self._outbox_table)
        async with session.connection.cursor() as cursor:
            await cursor.execute(sql)

    async def _create_offsets_table(self, session: 'IPgSession') -> None:
        """Create offsets table for consumer groups."""
        sql = """
            CREATE TABLE IF NOT EXISTS %s (
                "consumer_group" VARCHAR(255) NOT NULL,
                "offset_acked" BIGINT NOT NULL DEFAULT 0,
                "last_processed_transaction_id" xid8 NOT NULL DEFAULT '0',
                "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY ("consumer_group")
            )
        """ % (self._offsets_table,)
        async with session.connection.cursor() as cursor:
            await cursor.execute(sql)

    async def cleanup(self) -> None:
        """Cleanup resources."""
        pass

    async def get_position(
            self,
            session: 'IPgSession',
            consumer_group: str = ''
    ) -> tuple[int, int]:
        """Get current position for a consumer group."""
        sql = """
            SELECT last_processed_transaction_id, offset_acked
            FROM %s
            WHERE consumer_group = %%(consumer_group)s
        """ % (self._offsets_table,)

        async with session.connection.cursor() as cursor:
            await cursor.execute(sql, {'consumer_group': consumer_group})
            row = await cursor.fetchone()
            if row is None:
                return (0, 0)
            return (int(row[0]), row[1])

    async def set_position(
            self,
            session: 'IPgSession',
            consumer_group: str,
            transaction_id: int,
            offset: int
    ) -> None:
        """Set position for a consumer group."""
        sql = """
            INSERT INTO %s (consumer_group, offset_acked, last_processed_transaction_id, updated_at)
            VALUES (%%(consumer_group)s, %%(offset)s, %%(transaction_id)s, CURRENT_TIMESTAMP)
            ON CONFLICT (consumer_group) DO UPDATE SET
                offset_acked = EXCLUDED.offset_acked,
                last_processed_transaction_id = EXCLUDED.last_processed_transaction_id,
                updated_at = EXCLUDED.updated_at
        """ % (self._offsets_table,)

        async with session.connection.cursor() as cursor:
            await cursor.execute(sql, {
                'consumer_group': consumer_group,
                'offset': offset,
                'transaction_id': str(transaction_id),
            })

    # Private methods

    async def _ensure_consumer_group(self, session: 'IPgSession', consumer_group: str) -> None:
        """Ensure consumer group exists with zero position.

        Required for FOR UPDATE locking to work (can't lock non-existent row).
        """
        sql = """
            INSERT INTO %s (consumer_group, offset_acked, last_processed_transaction_id)
            VALUES (%%(consumer_group)s, 0, '0')
            ON CONFLICT DO NOTHING
        """ % (self._offsets_table,)

        async with session.connection.cursor() as cursor:
            await cursor.execute(sql, {'consumer_group': consumer_group})

    async def _fetch_messages(
            self,
            session: 'IPgSession',
            consumer_group: str
    ) -> list['OutboxMessage']:
        """Fetch next batch of messages with FOR UPDATE lock.

        Uses subquery wrapper to avoid query planner mis-estimation with ORDER BY + LIMIT.
        See watermill-sql comments for details.

        Note: _ensure_consumer_group must be called before this method.
        """
        # Query with subquery wrapper for query planner optimization
        sql = """
            SELECT * FROM (
                WITH last_processed AS (
                    SELECT offset_acked, last_processed_transaction_id
                    FROM %s
                    WHERE consumer_group = %%(consumer_group)s
                    FOR UPDATE
                )
                SELECT "position", transaction_id, event_type, event_version, payload, metadata, created_at
                FROM %s
                WHERE (
                    (transaction_id = (SELECT last_processed_transaction_id FROM last_processed)
                     AND "position" > (SELECT offset_acked FROM last_processed))
                    OR
                    (transaction_id > (SELECT last_processed_transaction_id FROM last_processed))
                )
                AND transaction_id < pg_snapshot_xmin(pg_current_snapshot())
            ) AS messages
            ORDER BY transaction_id ASC, "position" ASC
            LIMIT %d
        """ % (self._offsets_table, self._outbox_table, self._batch_size)

        async with session.connection.cursor() as cursor:
            await cursor.execute(sql, {'consumer_group': consumer_group})
            rows = await cursor.fetchall()

        return [self._row_to_message(row) for row in rows]

    async def _ack_message(
            self,
            session: 'IPgSession',
            consumer_group: str,
            transaction_id: int,
            position: int
    ) -> None:
        """Acknowledge message by updating consumer position."""
        sql = """
            INSERT INTO %s (consumer_group, offset_acked, last_processed_transaction_id, updated_at)
            VALUES (%%(consumer_group)s, %%(position)s, %%(transaction_id)s, CURRENT_TIMESTAMP)
            ON CONFLICT (consumer_group) DO UPDATE SET
                offset_acked = EXCLUDED.offset_acked,
                last_processed_transaction_id = EXCLUDED.last_processed_transaction_id,
                updated_at = EXCLUDED.updated_at
        """ % (self._offsets_table,)

        async with session.connection.cursor() as cursor:
            await cursor.execute(sql, {
                'consumer_group': consumer_group,
                'position': position,
                'transaction_id': str(transaction_id),
            })

    def _row_to_message(self, row: tuple) -> 'OutboxMessage':
        """Convert database row to OutboxMessage."""
        position, transaction_id, event_type, event_version, payload, metadata, created_at = row
        return OutboxMessage(
            event_type=event_type,
            payload=payload if isinstance(payload, dict) else {},
            metadata=metadata if isinstance(metadata, dict) else {},
            event_version=event_version,
            created_at=str(created_at) if created_at else None,
            position=position,
            transaction_id=int(transaction_id) if transaction_id else None,
        )

    @staticmethod
    def _to_jsonb(obj: dict) -> Jsonb:
        """Convert dict to Jsonb for psycopg."""
        return Jsonb(obj)
