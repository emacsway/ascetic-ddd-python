"""Integration tests for Inbox with PostgreSQL."""

import asyncio
import unittest
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.inbox.inbox import Inbox
from ascetic_ddd.inbox.message import InboxMessage
from ascetic_ddd.inbox.tests.integration.db import make_pg_session_pool


class TestInbox(Inbox):
    """Concrete Inbox implementation for testing."""

    _table: str = 'inbox_test'
    _sequence: str = 'inbox_test_received_position_seq'

    def __init__(self, session_pool):
        super().__init__(session_pool)
        self.handled_messages = []

    async def do_handle(self, session, message: InboxMessage) -> None:
        self.handled_messages.append(message)
        await super().do_handle(session, message)


class InboxIntegrationTestCase(IsolatedAsyncioTestCase):
    """Integration tests for Inbox with real PostgreSQL."""

    async def asyncSetUp(self):
        self.session_pool = await make_pg_session_pool()
        self.inbox = TestInbox(self.session_pool)
        await self.inbox.setup()
        await self._truncate_table()

    async def asyncTearDown(self):
        await self._drop_table()
        await self.session_pool._pool.close()

    async def _truncate_table(self):
        """Truncate inbox table before each test."""
        async with self.session_pool.session() as session:
            async with session.atomic():
                async with session.connection.cursor() as cursor:
                    await cursor.execute("TRUNCATE TABLE %s" % self.inbox._table)

    async def _drop_table(self):
        """Drop inbox table after tests."""
        async with self.session_pool.session() as session:
            async with session.atomic():
                async with session.connection.cursor() as cursor:
                    await cursor.execute("DROP TABLE IF EXISTS %s" % self.inbox._table)
                    await cursor.execute("DROP SEQUENCE IF EXISTS %s" % self.inbox._sequence)

    async def test_publish_and_dispatch(self):
        """publish() stores message, dispatch() processes it."""
        message = InboxMessage(
            tenant_id="tenant1",
            stream_type="Order",
            stream_id={"id": "order-123"},
            stream_position=1,
            event_type="OrderCreated",
            event_version=1,
            payload={"amount": 100},
            metadata={"event_id": "uuid-123"},
        )

        await self.inbox.publish(message)
        result = await self.inbox.dispatch()

        self.assertTrue(result)
        self.assertEqual(len(self.inbox.handled_messages), 1)
        self.assertEqual(self.inbox.handled_messages[0].tenant_id, "tenant1")
        self.assertEqual(self.inbox.handled_messages[0].stream_id, {"id": "order-123"})

    async def test_idempotency(self):
        """Duplicate messages are ignored."""
        message = InboxMessage(
            tenant_id="tenant1",
            stream_type="Order",
            stream_id={"id": "order-123"},
            stream_position=1,
            event_type="OrderCreated",
            event_version=1,
            payload={"amount": 100},
        )

        # Publish same message twice
        await self.inbox.publish(message)
        await self.inbox.publish(message)

        # Only one message should be processed
        await self.inbox.dispatch()
        result = await self.inbox.dispatch()

        self.assertFalse(result)
        self.assertEqual(len(self.inbox.handled_messages), 1)

    async def test_causal_dependencies(self):
        """Messages wait for dependencies to be processed."""
        # Message that depends on another
        dependent_message = InboxMessage(
            tenant_id="tenant1",
            stream_type="Order",
            stream_id={"id": "order-123"},
            stream_position=2,
            event_type="OrderShipped",
            event_version=1,
            payload={"tracking": "123"},
            metadata={
                "causal_dependencies": [
                    {
                        "tenant_id": "tenant1",
                        "stream_type": "Order",
                        "stream_id": {"id": "order-123"},
                        "stream_position": 1,
                    }
                ]
            },
        )

        # Publish dependent message first
        await self.inbox.publish(dependent_message)

        # Should not process (dependency not met)
        result = await self.inbox.dispatch()
        self.assertFalse(result)

        # Now publish the dependency
        dependency_message = InboxMessage(
            tenant_id="tenant1",
            stream_type="Order",
            stream_id={"id": "order-123"},
            stream_position=1,
            event_type="OrderCreated",
            event_version=1,
            payload={"amount": 100},
        )
        await self.inbox.publish(dependency_message)

        # Process dependency first
        result = await self.inbox.dispatch()
        self.assertTrue(result)
        self.assertEqual(self.inbox.handled_messages[0].event_type, "OrderCreated")

        # Now dependent message can be processed
        result = await self.inbox.dispatch()
        self.assertTrue(result)
        self.assertEqual(self.inbox.handled_messages[1].event_type, "OrderShipped")

    async def test_ordering_by_received_position(self):
        """Messages are processed in order of arrival."""
        for i in range(3):
            message = InboxMessage(
                tenant_id="tenant1",
                stream_type="Order",
                stream_id={"id": "order-%d" % i},
                stream_position=1,
                event_type="OrderCreated",
                event_version=1,
                payload={"order": i},
            )
            await self.inbox.publish(message)

        # Process all messages
        while await self.inbox.dispatch():
            pass

        self.assertEqual(len(self.inbox.handled_messages), 3)
        for i, msg in enumerate(self.inbox.handled_messages):
            self.assertEqual(msg.payload["order"], i)

    async def test_subscribe_decorator(self):
        """@inbox.subscribe registers handlers."""
        handled_events = []

        @self.inbox.subscribe("OrderCreated", event_version=1)
        async def handle_order_created(session, message):
            handled_events.append(("created", message.stream_id))

        @self.inbox.subscribe("OrderShipped", event_version=1)
        async def handle_order_shipped(session, message):
            handled_events.append(("shipped", message.stream_id))

        # Publish messages
        await self.inbox.publish(InboxMessage(
            tenant_id="tenant1",
            stream_type="Order",
            stream_id={"id": "order-1"},
            stream_position=1,
            event_type="OrderCreated",
            event_version=1,
            payload={},
        ))
        await self.inbox.publish(InboxMessage(
            tenant_id="tenant1",
            stream_type="Order",
            stream_id={"id": "order-2"},
            stream_position=1,
            event_type="OrderShipped",
            event_version=1,
            payload={},
        ))

        # Process messages
        await self.inbox.dispatch()
        await self.inbox.dispatch()

        self.assertEqual(len(handled_events), 2)
        self.assertEqual(handled_events[0], ("created", {"id": "order-1"}))
        self.assertEqual(handled_events[1], ("shipped", {"id": "order-2"}))

    async def test_async_iterator(self):
        """Async iterator yields messages."""
        for i in range(2):
            await self.inbox.publish(InboxMessage(
                tenant_id="tenant1",
                stream_type="Order",
                stream_id={"id": "order-%d" % i},
                stream_position=1,
                event_type="OrderCreated",
                event_version=1,
                payload={"order": i},
            ))

        messages = []
        iterator = self.inbox.__aiter__()

        # Get first message
        session, message = await iterator.__anext__()
        messages.append(message)

        # Get second message
        session, message = await iterator.__anext__()
        messages.append(message)

        await iterator.aclose()

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].payload["order"], 0)
        self.assertEqual(messages[1].payload["order"], 1)

    async def test_run_with_single_worker(self):
        """run() with single worker processes messages."""
        for i in range(3):
            await self.inbox.publish(InboxMessage(
                tenant_id="tenant1",
                stream_type="Order",
                stream_id={"id": "order-%d" % i},
                stream_position=1,
                event_type="OrderCreated",
                event_version=1,
                payload={"order": i},
            ))

        # Run with timeout
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(
                self.inbox.run(workers=1, poll_interval=0.01),
                timeout=0.2
            )

        self.assertEqual(len(self.inbox.handled_messages), 3)

    async def test_run_with_multiple_workers(self):
        """run() with multiple workers processes messages concurrently."""
        for i in range(10):
            await self.inbox.publish(InboxMessage(
                tenant_id="tenant1",
                stream_type="Order",
                stream_id={"id": "order-%d" % i},
                stream_position=1,
                event_type="OrderCreated",
                event_version=1,
                payload={"order": i},
            ))

        # Run with multiple workers and timeout
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(
                self.inbox.run(workers=3, poll_interval=0.01),
                timeout=0.3
            )

        # All messages should be processed (order may vary due to concurrency)
        self.assertEqual(len(self.inbox.handled_messages), 10)

    async def test_for_update_skip_locked(self):
        """Multiple workers don't process same message (FOR UPDATE SKIP LOCKED)."""
        # Publish a single message
        await self.inbox.publish(InboxMessage(
            tenant_id="tenant1",
            stream_type="Order",
            stream_id={"id": "order-1"},
            stream_position=1,
            event_type="OrderCreated",
            event_version=1,
            payload={},
        ))

        # Run with multiple workers
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(
                self.inbox.run(workers=3, poll_interval=0.01),
                timeout=0.1
            )

        # Message should be processed exactly once
        self.assertEqual(len(self.inbox.handled_messages), 1)


if __name__ == '__main__':
    unittest.main()
