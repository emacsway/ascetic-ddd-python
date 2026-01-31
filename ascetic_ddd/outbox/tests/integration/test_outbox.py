"""Integration tests for Outbox with PostgreSQL."""

import asyncio
import unittest
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.outbox.message import OutboxMessage
from ascetic_ddd.outbox.outbox import Outbox
from ascetic_ddd.outbox.tests.integration.db import make_pg_session_pool


class OutboxIntegrationTestCase(IsolatedAsyncioTestCase):
    """Integration tests for Outbox with real PostgreSQL."""

    _outbox_table: str = 'outbox_test'
    _offsets_table: str = 'outbox_offsets_test'

    async def asyncSetUp(self):
        self._session_pool = await make_pg_session_pool()
        self.outbox = Outbox(
            self._session_pool,
            outbox_table=self._outbox_table,
            offsets_table=self._offsets_table,
        )
        await self.outbox.setup()
        await self._truncate_tables()
        self.published_messages = []

    async def asyncTearDown(self):
        await self._drop_tables()
        await self._session_pool._pool.close()

    async def _truncate_tables(self):
        """Truncate tables before each test."""
        async with self._session_pool.session() as session:
            async with session.connection.cursor() as cursor:
                await cursor.execute("TRUNCATE TABLE %s" % self._outbox_table)
                await cursor.execute("TRUNCATE TABLE %s" % self._offsets_table)

    async def _drop_tables(self):
        """Drop tables after tests."""
        async with self._session_pool.session() as session:
            async with session.connection.cursor() as cursor:
                await cursor.execute("DROP TABLE IF EXISTS %s" % self._outbox_table)
                await cursor.execute("DROP TABLE IF EXISTS %s" % self._offsets_table)

    async def _publisher(self, message: OutboxMessage):
        """Test publisher that collects messages."""
        self.published_messages.append(message)

    async def test_publish_and_dispatch(self):
        """publish() stores message, dispatch() publishes it."""
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                message = OutboxMessage(
                    event_type="OrderCreated",
                    payload={"order_id": "123", "amount": 100},
                    metadata={"event_id": "550e8400-e29b-41d4-a716-446655440001"},
                )
                await self.outbox.publish(tx_session, message)

        result = await self.outbox.dispatch(self._publisher)

        self.assertTrue(result)
        self.assertEqual(len(self.published_messages), 1)
        self.assertEqual(self.published_messages[0].event_type, "OrderCreated")
        self.assertEqual(self.published_messages[0].payload["order_id"], "123")

    async def test_dispatch_returns_false_when_empty(self):
        """dispatch() returns False when no messages."""
        result = await self.outbox.dispatch(self._publisher)

        self.assertFalse(result)
        self.assertEqual(len(self.published_messages), 0)

    async def test_dispatch_updates_position(self):
        """dispatch() updates consumer position after publishing."""
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                message = OutboxMessage(
                    event_type="OrderCreated",
                    payload={"order_id": "123"},
                    metadata={"event_id": "550e8400-e29b-41d4-a716-446655440002"},
                )
                await self.outbox.publish(tx_session, message)

        await self.outbox.dispatch(self._publisher, consumer_group="test-group")

        # Dispatch again - should return False (no new messages)
        result = await self.outbox.dispatch(self._publisher, consumer_group="test-group")
        self.assertFalse(result)

    async def test_multiple_consumer_groups(self):
        """Different consumer groups track positions independently."""
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                message = OutboxMessage(
                    event_type="OrderCreated",
                    payload={"order_id": "123"},
                    metadata={"event_id": "550e8400-e29b-41d4-a716-446655440003"},
                )
                await self.outbox.publish(tx_session, message)

        # First consumer group
        result1 = await self.outbox.dispatch(self._publisher, consumer_group="group-1")
        self.assertTrue(result1)
        self.assertEqual(len(self.published_messages), 1)

        # Second consumer group - same message
        result2 = await self.outbox.dispatch(self._publisher, consumer_group="group-2")
        self.assertTrue(result2)
        self.assertEqual(len(self.published_messages), 2)

        # Both received the same event
        self.assertEqual(self.published_messages[0].event_type, "OrderCreated")
        self.assertEqual(self.published_messages[1].event_type, "OrderCreated")

    async def test_ordering_by_position(self):
        """Messages are dispatched in order of position."""
        async with self._session_pool.session() as session:
            for i in range(3):
                async with session.atomic() as tx_session:
                    message = OutboxMessage(
                        event_type="OrderCreated",
                        payload={"order": i},
                        metadata={"event_id": "550e8400-e29b-41d4-a716-44665544000%d" % i},
                    )
                    await self.outbox.publish(tx_session, message)

        # Dispatch all
        while await self.outbox.dispatch(self._publisher):
            pass

        self.assertEqual(len(self.published_messages), 3)
        for i, msg in enumerate(self.published_messages):
            self.assertEqual(msg.payload["order"], i)

    async def test_batch_dispatch(self):
        """dispatch() processes batch of messages."""
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                for i in range(5):
                    message = OutboxMessage(
                        event_type="OrderCreated",
                        payload={"order": i},
                        metadata={"event_id": "550e8400-e29b-41d4-a716-44665544010%d" % i},
                    )
                    await self.outbox.publish(tx_session, message)

        # Single dispatch should get all messages in batch
        result = await self.outbox.dispatch(self._publisher)

        self.assertTrue(result)
        self.assertEqual(len(self.published_messages), 5)

    async def test_get_and_set_position(self):
        """get_position() and set_position() work correctly."""
        async with self._session_pool.session() as session:
            # Initially (0, 0)
            pos = await self.outbox.get_position(session, "test-group")
            self.assertEqual(pos, (0, 0))

            # Set position
            await self.outbox.set_position(session, "test-group", transaction_id=100, offset=50)

            # Get updated position
            pos = await self.outbox.get_position(session, "test-group")
            self.assertEqual(pos, (100, 50))

    async def test_async_iterator(self):
        """Async iterator yields messages."""
        async with self._session_pool.session() as session:
            for i in range(2):
                async with session.atomic() as tx_session:
                    message = OutboxMessage(
                        event_type="OrderCreated",
                        payload={"order": i},
                        metadata={"event_id": "550e8400-e29b-41d4-a716-44665544020%d" % i},
                    )
                    await self.outbox.publish(tx_session, message)

        messages = []
        iterator = self.outbox.__aiter__()

        # Get first message
        message = await iterator.__anext__()
        messages.append(message)

        # Get second message
        message = await iterator.__anext__()
        messages.append(message)

        await iterator.aclose()

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].payload["order"], 0)
        self.assertEqual(messages[1].payload["order"], 1)

    async def test_run_with_single_worker(self):
        """run() with single worker processes messages."""
        async with self._session_pool.session() as session:
            for i in range(3):
                async with session.atomic() as tx_session:
                    message = OutboxMessage(
                        event_type="OrderCreated",
                        payload={"order": i},
                        metadata={"event_id": "550e8400-e29b-41d4-a716-44665544030%d" % i},
                    )
                    await self.outbox.publish(tx_session, message)

        # Run with timeout
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(
                self.outbox.run(self._publisher, workers=1, poll_interval=0.01),
                timeout=0.2
            )

        self.assertEqual(len(self.published_messages), 3)

    async def test_run_with_multiple_workers(self):
        """run() with multiple workers processes messages."""
        async with self._session_pool.session() as session:
            for i in range(10):
                async with session.atomic() as tx_session:
                    message = OutboxMessage(
                        event_type="OrderCreated",
                        payload={"order": i},
                        metadata={"event_id": "550e8400-e29b-41d4-a716-44665544040%d" % i},
                    )
                    await self.outbox.publish(tx_session, message)

        # Run with multiple workers and timeout
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(
                self.outbox.run(self._publisher, workers=3, poll_interval=0.01),
                timeout=0.3
            )

        # All messages should be processed
        self.assertEqual(len(self.published_messages), 10)

    async def test_visibility_rule(self):
        """Messages from uncommitted transactions are not visible."""
        # Start transaction but don't commit
        async with self._session_pool._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        INSERT INTO %s (event_type, event_version, payload, metadata, transaction_id)
                        VALUES ('OrderCreated', 1, '{"order": 1}'::jsonb,
                                '{"event_id": "550e8400-e29b-41d4-a716-446655440050"}'::jsonb,
                                pg_current_xact_id())
                    """ % self._outbox_table)

                    # Before commit - message should not be visible to dispatcher
                    result = await self.outbox.dispatch(self._publisher)
                    self.assertFalse(result)

                # Transaction commits here

        # After commit - message should be visible
        result = await self.outbox.dispatch(self._publisher)
        self.assertTrue(result)
        self.assertEqual(len(self.published_messages), 1)

    async def test_idempotency_via_event_id(self):
        """Duplicate event_id causes unique constraint violation."""
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                message = OutboxMessage(
                    event_type="OrderCreated",
                    payload={"order_id": "123"},
                    metadata={"event_id": "550e8400-e29b-41d4-a716-446655440060"},
                )
                await self.outbox.publish(tx_session, message)

        # Try to insert duplicate
        with self.assertRaises(Exception):  # UniqueViolation
            async with self._session_pool.session() as session:
                async with session.atomic() as tx_session:
                    message = OutboxMessage(
                        event_type="OrderCreated",
                        payload={"order_id": "456"},
                        metadata={"event_id": "550e8400-e29b-41d4-a716-446655440060"},
                    )
                    await self.outbox.publish(tx_session, message)


class OutboxConcurrencyTestCase(IsolatedAsyncioTestCase):
    """Tests for concurrent dispatcher behavior."""

    _outbox_table: str = 'outbox_concurrency_test'
    _offsets_table: str = 'outbox_offsets_concurrency_test'

    async def asyncSetUp(self):
        self._session_pool = await make_pg_session_pool()
        self.outbox = Outbox(
            self._session_pool,
            outbox_table=self._outbox_table,
            offsets_table=self._offsets_table,
        )
        await self.outbox.setup()
        await self._truncate_tables()
        self.published_messages = []

    async def asyncTearDown(self):
        await self._drop_tables()
        await self._session_pool._pool.close()

    async def _truncate_tables(self):
        """Truncate tables before each test."""
        async with self._session_pool.session() as session:
            async with session.connection.cursor() as cursor:
                await cursor.execute("TRUNCATE TABLE %s" % self._outbox_table)
                await cursor.execute("TRUNCATE TABLE %s" % self._offsets_table)

    async def _drop_tables(self):
        """Drop tables after tests."""
        async with self._session_pool.session() as session:
            async with session.connection.cursor() as cursor:
                await cursor.execute("DROP TABLE IF EXISTS %s" % self._outbox_table)
                await cursor.execute("DROP TABLE IF EXISTS %s" % self._offsets_table)

    async def _publisher(self, message: OutboxMessage):
        """Test publisher that collects messages with small delay."""
        await asyncio.sleep(0.01)  # Simulate network delay
        self.published_messages.append(message)

    async def test_for_update_prevents_duplicate_processing(self):
        """FOR UPDATE lock prevents duplicate message processing."""
        # Publish single message
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                message = OutboxMessage(
                    event_type="OrderCreated",
                    payload={"order_id": "123"},
                    metadata={"event_id": "550e8400-e29b-41d4-a716-446655440070"},
                )
                await self.outbox.publish(tx_session, message)

        # Run multiple concurrent dispatchers
        results = await asyncio.gather(
            self.outbox.dispatch(self._publisher, "test-group"),
            self.outbox.dispatch(self._publisher, "test-group"),
            self.outbox.dispatch(self._publisher, "test-group"),
        )

        # Only one should succeed
        self.assertEqual(sum(results), 1)
        self.assertEqual(len(self.published_messages), 1)


if __name__ == '__main__':
    unittest.main()
