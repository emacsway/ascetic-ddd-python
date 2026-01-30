"""Tests for Inbox class."""

import json
import unittest
from typing import Any
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.inbox.inbox import Inbox
from ascetic_ddd.inbox.message import InboxMessage


class MockCursor:
    """Mock database cursor."""

    def __init__(self, rows: list = None):
        self._rows = rows or []
        self._index = 0
        self.executed_sql = []
        self.executed_params = []

    async def execute(self, sql: str, params: tuple = None):
        self.executed_sql.append(sql)
        self.executed_params.append(params)

    async def fetchone(self):
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return row
        return None

    async def fetchall(self):
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockConnection:
    """Mock database connection."""

    def __init__(self, cursor: MockCursor = None):
        self._cursor = cursor or MockCursor()

    def cursor(self):
        return self._cursor


class MockSession:
    """Mock database session."""

    def __init__(self, connection: MockConnection = None):
        self._connection = connection or MockConnection()

    @property
    def connection(self):
        return self._connection

    def atomic(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockSessionPool:
    """Mock session pool."""

    def __init__(self, session: MockSession = None):
        self._session = session or MockSession()

    def session(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass


class TestInbox(Inbox):
    """Concrete Inbox implementation for testing."""

    def __init__(self, session_pool):
        super().__init__(session_pool)
        self.handled_messages = []

    async def do_handle(self, session, message: InboxMessage) -> None:
        self.handled_messages.append(message)


class InboxReceiveTestCase(IsolatedAsyncioTestCase):
    """Test cases for Inbox.publish()."""

    async def test_receive_inserts_message(self):
        """publish() inserts message into database."""
        cursor = MockCursor()
        connection = MockConnection(cursor)
        session = MockSession(connection)
        pool = MockSessionPool(session)

        inbox = TestInbox(pool)
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

        await inbox.publish(message)

        self.assertEqual(len(cursor.executed_sql), 1)
        self.assertIn("INSERT INTO", cursor.executed_sql[0])
        self.assertIn("ON CONFLICT", cursor.executed_sql[0])

        params = cursor.executed_params[0]
        self.assertEqual(params[0], "tenant1")
        self.assertEqual(params[1], "Order")
        self.assertEqual(params[2], '{"id": "order-123"}')
        self.assertEqual(params[3], 1)
        self.assertEqual(params[4], "OrderCreated")
        self.assertEqual(params[5], 1)


class InboxHandleTestCase(IsolatedAsyncioTestCase):
    """Test cases for Inbox.handle()."""

    async def test_handle_returns_false_when_no_messages(self):
        """handle() returns False when no unprocessed messages."""
        cursor = MockCursor(rows=[])
        connection = MockConnection(cursor)
        session = MockSession(connection)
        pool = MockSessionPool(session)

        inbox = TestInbox(pool)
        result = await inbox.handle()

        self.assertFalse(result)
        self.assertEqual(len(inbox.handled_messages), 0)

    async def test_handle_processes_message_without_dependencies(self):
        """handle() processes message without causal dependencies."""
        row = (
            "tenant1",  # tenant_id
            "Order",  # stream_type
            {"id": "order-123"},  # stream_id
            1,  # stream_position
            "OrderCreated",  # event_type
            1,  # event_version
            {"amount": 100},  # payload
            None,  # metadata
            1,  # received_position
            None,  # processed_position
        )
        cursor = MockCursor(rows=[row])
        connection = MockConnection(cursor)
        session = MockSession(connection)
        pool = MockSessionPool(session)

        inbox = TestInbox(pool)
        result = await inbox.handle()

        self.assertTrue(result)
        self.assertEqual(len(inbox.handled_messages), 1)
        self.assertEqual(inbox.handled_messages[0].tenant_id, "tenant1")


class InboxDependencyCheckTestCase(IsolatedAsyncioTestCase):
    """Test cases for causal dependency checking."""

    async def test_dependencies_satisfied_when_empty(self):
        """Message with no dependencies is processable."""
        message = InboxMessage(
            tenant_id="tenant1",
            stream_type="Order",
            stream_id={"id": "order-123"},
            stream_position=1,
            event_type="OrderCreated",
            event_version=1,
            payload={},
            metadata=None,
        )

        cursor = MockCursor()
        connection = MockConnection(cursor)
        session = MockSession(connection)
        pool = MockSessionPool(session)

        inbox = TestInbox(pool)
        result = await inbox._are_dependencies_satisfied(session, message)

        self.assertTrue(result)

    async def test_dependency_satisfied_when_processed(self):
        """Dependency is satisfied when it exists and is processed."""
        cursor = MockCursor(rows=[(1,)])  # Row exists
        connection = MockConnection(cursor)
        session = MockSession(connection)
        pool = MockSessionPool(session)

        inbox = TestInbox(pool)
        dep = {
            "tenant_id": "tenant1",
            "stream_type": "User",
            "stream_id": {"id": "user-1"},
            "stream_position": 5,
        }

        result = await inbox._is_dependency_processed(session, dep)

        self.assertTrue(result)

    async def test_dependency_not_satisfied_when_missing(self):
        """Dependency is not satisfied when it doesn't exist."""
        cursor = MockCursor(rows=[])  # No row
        connection = MockConnection(cursor)
        session = MockSession(connection)
        pool = MockSessionPool(session)

        inbox = TestInbox(pool)
        dep = {
            "tenant_id": "tenant1",
            "stream_type": "User",
            "stream_id": {"id": "user-1"},
            "stream_position": 5,
        }

        result = await inbox._is_dependency_processed(session, dep)

        self.assertFalse(result)


class InboxSetupTestCase(IsolatedAsyncioTestCase):
    """Test cases for Inbox.setup()."""

    async def test_setup_creates_sequence_and_table(self):
        """setup() creates sequence and table."""
        cursor = MockCursor()
        connection = MockConnection(cursor)
        session = MockSession(connection)
        pool = MockSessionPool(session)

        inbox = TestInbox(pool)
        await inbox.setup()

        self.assertEqual(len(cursor.executed_sql), 2)
        self.assertIn("CREATE SEQUENCE", cursor.executed_sql[0])
        self.assertIn("CREATE TABLE", cursor.executed_sql[1])


class InboxAsyncIteratorTestCase(IsolatedAsyncioTestCase):
    """Test cases for Inbox async iterator."""

    async def test_aiter_yields_session_and_message(self):
        """Async iterator yields (session, message) tuples."""
        row = (
            "tenant1",
            "Order",
            {"id": "order-123"},
            1,
            "OrderCreated",
            1,
            {"amount": 100},
            None,
            1,
            None,
        )
        # First call returns row, second returns None (to stop iteration)
        cursor = MockCursor(rows=[row, None])
        connection = MockConnection(cursor)
        session = MockSession(connection)
        pool = MockSessionPool(session)

        inbox = TestInbox(pool)
        results = []

        # Use anext to get one item without infinite loop
        iterator = inbox.__aiter__()
        session_result, message_result = await iterator.__anext__()

        self.assertIsNotNone(session_result)
        self.assertEqual(message_result.tenant_id, "tenant1")
        self.assertEqual(message_result.event_type, "OrderCreated")

    async def test_aiter_marks_message_as_processed(self):
        """Async iterator marks message as processed after yield."""
        row = (
            "tenant1",
            "Order",
            {"id": "order-123"},
            1,
            "OrderCreated",
            1,
            {"amount": 100},
            None,
            1,
            None,
        )
        cursor = MockCursor(rows=[row])
        connection = MockConnection(cursor)
        session = MockSession(connection)
        pool = MockSessionPool(session)

        inbox = TestInbox(pool)

        iterator = inbox.__aiter__()
        await iterator.__anext__()
        # Close the generator to ensure code after yield executes
        await iterator.aclose()

        # Check that UPDATE was executed to mark as processed
        update_sqls = [sql for sql in cursor.executed_sql if "UPDATE" in sql]
        self.assertEqual(len(update_sqls), 1)
        self.assertIn("processed_position", update_sqls[0])


if __name__ == '__main__':
    unittest.main()
