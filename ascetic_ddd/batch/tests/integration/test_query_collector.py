"""Integration tests for QueryCollector with PostgreSQL."""

import unittest
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.batch.query_collector import QueryCollector
from ascetic_ddd.utils.tests.db import make_pg_session_pool


class QueryCollectorIntegrationTestCase(IsolatedAsyncioTestCase):
    """Integration tests for QueryCollector with real PostgreSQL."""

    _test_table: str = 'batch_test'

    async def asyncSetUp(self):
        self._session_pool = await make_pg_session_pool()
        await self._create_table()

    async def asyncTearDown(self):
        await self._drop_table()
        await self._session_pool._pool.close()

    async def _create_table(self):
        """Create test table."""
        async with self._session_pool.session() as session:
            await session.connection.execute("""
                CREATE TABLE IF NOT EXISTS %s (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    value INTEGER NOT NULL
                )
            """ % self._test_table)

    async def _drop_table(self):
        """Drop test table."""
        async with self._session_pool.session() as session:
            await session.connection.execute(
                "DROP TABLE IF EXISTS %s" % self._test_table
            )

    async def _truncate_table(self):
        """Truncate test table."""
        async with self._session_pool.session() as session:
            await session.connection.execute(
                "TRUNCATE TABLE %s RESTART IDENTITY" % self._test_table
            )

    async def _count_rows(self) -> int:
        """Count rows in test table."""
        async with self._session_pool.session() as session:
            cursor = await session.connection.execute(
                "SELECT COUNT(*) FROM %s" % self._test_table
            )
            row = await cursor.fetchone()
            return row[0]

    async def _get_all_rows(self) -> list:
        """Get all rows from test table."""
        async with self._session_pool.session() as session:
            cursor = await session.connection.execute(
                "SELECT id, name, value FROM %s ORDER BY id" % self._test_table
            )
            return await cursor.fetchall()

    async def test_multi_query_batches_inserts_without_returning(self):
        """MultiQuery batches multiple INSERTs without RETURNING."""
        await self._truncate_table()

        collector = QueryCollector()
        query = "INSERT INTO %s (name, value) VALUES (%%s, %%s)" % self._test_table

        # Collect multiple inserts
        d1 = await collector.connection.execute(query, ("item1", 10))
        d2 = await collector.connection.execute(query, ("item2", 20))
        d3 = await collector.connection.execute(query, ("item3", 30))

        # Verify deferreds are not resolved yet
        self.assertFalse(d1._last_result._is_resolved)
        self.assertFalse(d2._last_result._is_resolved)
        self.assertFalse(d3._last_result._is_resolved)

        # Execute batch
        async with self._session_pool.session() as session:
            await collector.evaluate(session)

        # Verify all rows inserted
        count = await self._count_rows()
        self.assertEqual(count, 3)

        rows = await self._get_all_rows()
        self.assertEqual(rows[0][1], "item1")
        self.assertEqual(rows[0][2], 10)
        self.assertEqual(rows[1][1], "item2")
        self.assertEqual(rows[1][2], 20)
        self.assertEqual(rows[2][1], "item3")
        self.assertEqual(rows[2][2], 30)

        # Verify deferreds are resolved
        self.assertTrue(d1._last_result._is_resolved)
        self.assertTrue(d2._last_result._is_resolved)
        self.assertTrue(d3._last_result._is_resolved)

    async def test_autoincrement_multi_insert_query_returns_ids(self):
        """AutoincrementMultiInsertQuery batches INSERTs with RETURNING."""
        await self._truncate_table()

        collector = QueryCollector()
        query = "INSERT INTO %s (name, value) VALUES (%%s, %%s) RETURNING id" % self._test_table

        # Collect multiple inserts with RETURNING
        d1 = await collector.connection.execute(query, ("item1", 100))
        d2 = await collector.connection.execute(query, ("item2", 200))
        d3 = await collector.connection.execute(query, ("item3", 300))

        # Capture returned IDs via callbacks
        returned_ids = []

        def capture_id(row):
            if row is not None:
                returned_ids.append(row[0])
            return None

        d1._last_result.then(capture_id, lambda e: None)
        d2._last_result.then(capture_id, lambda e: None)
        d3._last_result.then(capture_id, lambda e: None)

        # Execute batch
        async with self._session_pool.session() as session:
            await collector.evaluate(session)

        # Verify all rows inserted
        count = await self._count_rows()
        self.assertEqual(count, 3)

        # Verify IDs returned correctly
        self.assertEqual(len(returned_ids), 3)
        self.assertEqual(returned_ids, [1, 2, 3])

        # Verify deferreds have correct values
        self.assertEqual(d1._last_result._value[0], 1)
        self.assertEqual(d2._last_result._value[0], 2)
        self.assertEqual(d3._last_result._value[0], 3)

    async def test_mixed_queries_batched_separately(self):
        """Different query templates are batched separately."""
        await self._truncate_table()

        collector = QueryCollector()
        query_no_return = "INSERT INTO %s (name, value) VALUES (%%s, %%s)" % self._test_table
        query_with_return = "INSERT INTO %s (name, value) VALUES (%%s, %%s) RETURNING id" % self._test_table

        # Mix queries
        await collector.connection.execute(query_no_return, ("no_return_1", 1))
        d_return_1 = await collector.connection.execute(query_with_return, ("with_return_1", 10))
        await collector.connection.execute(query_no_return, ("no_return_2", 2))
        d_return_2 = await collector.connection.execute(query_with_return, ("with_return_2", 20))

        returned_ids = []

        def capture_id(row):
            if row is not None:
                returned_ids.append(row[0])
            return None

        d_return_1._last_result.then(capture_id, lambda e: None)
        d_return_2._last_result.then(capture_id, lambda e: None)

        # Execute batch
        async with self._session_pool.session() as session:
            await collector.evaluate(session)

        # Verify all rows inserted
        count = await self._count_rows()
        self.assertEqual(count, 4)

        # Verify RETURNING queries got IDs
        self.assertEqual(len(returned_ids), 2)

    async def test_callback_error_collected(self):
        """Errors in deferred callbacks are collected and raised."""
        await self._truncate_table()

        collector = QueryCollector()
        query = "INSERT INTO %s (name, value) VALUES (%%s, %%s) RETURNING id" % self._test_table

        d1 = await collector.connection.execute(query, ("item1", 100))

        def failing_callback(row):
            raise ValueError("Callback failed!")

        d1._last_result.then(failing_callback, lambda e: None)

        # Execute batch - should raise ExceptionGroup
        async with self._session_pool.session() as session:
            with self.assertRaises(ExceptionGroup) as ctx:
                await collector.evaluate(session)

            self.assertEqual(len(ctx.exception.exceptions), 1)
            self.assertIsInstance(ctx.exception.exceptions[0], ValueError)

        # Data should still be inserted
        count = await self._count_rows()
        self.assertEqual(count, 1)

    async def test_nested_inserts_via_callback(self):
        """Inserts added via callbacks are processed in subsequent iteration."""
        await self._truncate_table()

        collector = QueryCollector()
        query = "INSERT INTO %s (name, value) VALUES (%%s, %%s) RETURNING id" % self._test_table

        d1 = await collector.connection.execute(query, ("parent", 1))

        # Callback that adds another insert
        async def add_child(row):
            if row is not None:
                # Add child insert when parent is resolved
                await collector.connection.execute(query, ("child_of_%d" % row[0], row[0] * 10))
            return None

        # Note: This won't work with sync callback - need to test the pattern differently
        # For now, test that nested queries added during evaluation are processed

        returned_ids = []

        def capture_and_add_nested(row):
            if row is not None:
                returned_ids.append(row[0])
                # Add nested query synchronously
                collector._collect_query(query, ("nested_%d" % row[0], row[0] * 100))
            return None

        d1._last_result.then(capture_and_add_nested, lambda e: None)

        # Execute batch - should process both original and nested
        async with self._session_pool.session() as session:
            await collector.evaluate(session)

        # Verify both rows inserted
        count = await self._count_rows()
        self.assertEqual(count, 2)

        rows = await self._get_all_rows()
        self.assertEqual(rows[0][1], "parent")
        self.assertEqual(rows[1][1], "nested_1")

    async def test_large_batch(self):
        """Large batch of inserts is handled correctly."""
        await self._truncate_table()

        collector = QueryCollector()
        query = "INSERT INTO %s (name, value) VALUES (%%s, %%s)" % self._test_table

        # Collect many inserts
        batch_size = 100
        for i in range(batch_size):
            await collector.connection.execute(query, ("item_%d" % i, i))

        # Execute batch
        async with self._session_pool.session() as session:
            await collector.evaluate(session)

        # Verify all rows inserted
        count = await self._count_rows()
        self.assertEqual(count, batch_size)

    async def test_string_with_escaped_quotes(self):
        """Strings with escaped quotes are handled correctly."""
        await self._truncate_table()

        collector = QueryCollector()
        query = "INSERT INTO %s (name, value) VALUES (%%s, %%s)" % self._test_table

        # Insert strings with special characters
        await collector.connection.execute(query, ("someone's item", 1))
        await collector.connection.execute(query, ("item with 'quotes'", 2))
        await collector.connection.execute(query, ("normal item", 3))

        # Execute batch
        async with self._session_pool.session() as session:
            await collector.evaluate(session)

        # Verify all rows inserted correctly
        rows = await self._get_all_rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][1], "someone's item")
        self.assertEqual(rows[1][1], "item with 'quotes'")
        self.assertEqual(rows[2][1], "normal item")


if __name__ == '__main__':
    unittest.main()
