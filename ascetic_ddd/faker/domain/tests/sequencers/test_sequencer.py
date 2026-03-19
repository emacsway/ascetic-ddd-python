from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.faker.domain.sequencers.factory import sequencer_factory
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.scope_specification import ScopeSpecification
from ascetic_ddd.faker.infrastructure.tests.db import make_internal_pg_session_pool

# logging.basicConfig(level="DEBUG")


class SequencerTestCase(IsolatedAsyncioTestCase):
    sequencer_factory = staticmethod(sequencer_factory)

    async def _make_session_pool(self):
        return await make_internal_pg_session_pool()

    async def asyncSetUp(self):
        self.null_weight = 0
        self.session_pool = await self._make_session_pool()
        self.sequencer = self.sequencer_factory()
        self.sequencer.provider_name = 'path.Fk.fk_id'

    async def _next(self, ts_session, specification=None):
        if specification is None:
            specification = EmptySpecification()
        return await self.sequencer.next(ts_session, specification)

    async def test_default_key(self):
        count = 10

        async with self.session_pool.session() as session, session.atomic() as ts_session:
            result = [await self._next(ts_session) for _ in range(count)]

        self.assertListEqual(
            result,
            list(range(count))
        )

    async def test_specific_key(self):
        count = 10

        async with self.session_pool.session() as session, session.atomic() as ts_session:
            result = [await self._next(ts_session, ScopeSpecification(2)) for _ in range(count)]

        self.assertListEqual(
            result,
            list(range(count))
        )

        async with self.session_pool.session() as session, session.atomic() as ts_session:
            result = [await self._next(ts_session, ScopeSpecification(3)) for _ in range(count)]

        self.assertListEqual(
            result,
            list(range(count))
        )

    async def asyncTearDown(self):
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await self.sequencer.cleanup(ts_session)
        await self.session_pool._pool.close()
