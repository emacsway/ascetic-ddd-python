import uuid
import dataclasses
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.faker.domain.distributors.m2o.write_distributor import WriteDistributor, Index
from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.query_lookup_specification import QueryLookupSpecification
from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.faker.infrastructure.tests.db import make_internal_pg_session_pool

# logging.basicConfig(level="DEBUG")


@dataclasses.dataclass(kw_only=True)
class SomePk:
    id: uuid.UUID
    tenant_id: uuid.UUID

    def __hash__(self):
        return hash((self.id, self.tenant_id))


# =============================================================================
# Index tests
# =============================================================================

class IndexTestCase(IsolatedAsyncioTestCase):
    """Tests for Index with hashable and unhashable values."""

    def test_append_hashable(self):
        index = Index(EmptySpecification())
        pk = SomePk(id=uuid.uuid4(), tenant_id=uuid.uuid4())
        index.append(pk)
        self.assertEqual(len(index), 1)
        self.assertIn(pk, index)

    def test_append_duplicate_hashable(self):
        index = Index(EmptySpecification())
        pk = SomePk(id=uuid.uuid4(), tenant_id=uuid.uuid4())
        index.append(pk)
        index.append(pk)
        self.assertEqual(len(index), 1)

    def test_append_unhashable_dict(self):
        index = Index(EmptySpecification())
        value = {'id': uuid.uuid4(), 'tenant_id': uuid.uuid4()}
        index.append(value)
        self.assertEqual(len(index), 1)
        self.assertIn(value, index)

    def test_append_duplicate_unhashable_dict(self):
        index = Index(EmptySpecification())
        value = {'id': uuid.uuid4(), 'tenant_id': uuid.uuid4()}
        index.append(value)
        index.append(value)
        self.assertEqual(len(index), 1)

    def test_remove_hashable(self):
        index = Index(EmptySpecification())
        pk = SomePk(id=uuid.uuid4(), tenant_id=uuid.uuid4())
        index.append(pk)
        self.assertTrue(index.remove(pk))
        self.assertEqual(len(index), 0)
        self.assertNotIn(pk, index)

    def test_remove_unhashable(self):
        index = Index(EmptySpecification())
        value = {'id': uuid.uuid4(), 'tenant_id': uuid.uuid4()}
        index.append(value)
        self.assertTrue(index.remove(value))
        self.assertEqual(len(index), 0)

    def test_remove_nonexistent(self):
        index = Index(EmptySpecification())
        self.assertFalse(index.remove(42))

    def test_get_relative_position(self):
        index = Index(EmptySpecification())
        values = [10, 20, 30, 40]
        for v in values:
            index.append(v)
        self.assertAlmostEqual(index.get_relative_position(10), 0.0)
        self.assertAlmostEqual(index.get_relative_position(20), 0.25)
        self.assertIsNone(index.get_relative_position(99))

    def test_insert_at_relative_position(self):
        index = Index(EmptySpecification())
        for v in [10, 20, 30]:
            index.append(v)
        index.insert_at_relative_position(15, 0.33)
        self.assertEqual(len(index), 4)
        self.assertIn(15, index)


# =============================================================================
# WriteDistributor tests (public API — shared with PgWriteDistributor)
# =============================================================================

class WriteDistributorTestCase(IsolatedAsyncioTestCase):
    """Tests for WriteDistributor via public API (next, append)."""

    async def _make_session_pool(self):
        return await make_internal_pg_session_pool()

    async def asyncSetUp(self):
        self.session_pool = await self._make_session_pool()
        self.store = WriteDistributor(mean=10000)
        self.store.provider_name = 'test.write_distributor'

    async def test_next_always_raises_cursor(self):
        """next() always raises ICursor."""
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            with self.assertRaises(Cursor):
                await self.store.next(ts_session, EmptySpecification())

    async def test_provider_name(self):
        """provider_name is set once."""
        store = WriteDistributor()
        store.provider_name = 'first'
        store.provider_name = 'second'
        self.assertEqual(store.provider_name, 'first')

    async def asyncTearDown(self):
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await self.store.cleanup(ts_session)
        await self.session_pool._pool.close()


# =============================================================================
# WriteDistributor-specific tests (in-memory internals)
# =============================================================================

class WriteDistributorInMemoryTestCase(IsolatedAsyncioTestCase):
    """Tests for WriteDistributor in-memory specifics (next_with_strategy, indexes)."""

    async def _make_session_pool(self):
        return await make_internal_pg_session_pool()

    async def asyncSetUp(self):
        self.session_pool = await self._make_session_pool()
        self.store = WriteDistributor(mean=10000)
        self.store.provider_name = 'test.write_distributor_mem'

    async def test_next_with_strategy(self):
        """next_with_strategy returns stored values using distribution strategy."""
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            for i in range(10):
                await self.store.append(ts_session, i)

            result = await self.store.next_with_strategy(
                ts_session, EmptySpecification(), lambda n: 0
            )
            self.assertEqual(result.unwrap(), 0)

    async def test_next_with_strategy_empty_raises_cursor(self):
        """next_with_strategy raises ICursor when store is empty."""
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            with self.assertRaises(Cursor):
                await self.store.next_with_strategy(
                    ts_session, EmptySpecification(), lambda n: 0
                )

    async def test_next_with_strategy_filtered(self):
        """next_with_strategy filters by specification."""
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            tenant_a = uuid.uuid4()
            tenant_b = uuid.uuid4()
            pk_a = SomePk(id=uuid.uuid4(), tenant_id=tenant_a)
            pk_b = SomePk(id=uuid.uuid4(), tenant_id=tenant_b)
            await self.store.append(ts_session, pk_a)
            await self.store.append(ts_session, pk_b)

            spec = QueryLookupSpecification(
                QueryParser().parse({'tenant_id': {'$eq': tenant_a}}),
                lambda obj: dataclasses.asdict(obj),
            )
            result = await self.store.next_with_strategy(
                ts_session, spec, lambda n: 0
            )
            self.assertEqual(result.unwrap().tenant_id, tenant_a)

    async def test_shared_store_values_visible(self):
        """Values from cursor and append are both visible via next_with_strategy."""
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            try:
                await self.store.next(ts_session, EmptySpecification())
            except Cursor as cursor:
                await cursor.append(ts_session, 100)

            await self.store.append(ts_session, 200)

            results = set()
            for _ in range(50):
                result = await self.store.next_with_strategy(
                    ts_session, EmptySpecification(), lambda n: 0
                )
                results.add(result.unwrap())
                result = await self.store.next_with_strategy(
                    ts_session, EmptySpecification(), lambda n: n - 1
                )
                results.add(result.unwrap())
            self.assertIn(100, results)
            self.assertIn(200, results)

    async def asyncTearDown(self):
        await self.session_pool._pool.close()
