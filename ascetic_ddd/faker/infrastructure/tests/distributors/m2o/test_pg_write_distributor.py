from ascetic_ddd.faker.infrastructure.distributors.m2o.pg_write_distributor import PgWriteDistributor
from ascetic_ddd.faker.domain.tests.distributors.m2o import test_write_distributor as td


# logging.basicConfig(level="DEBUG")


class PgWriteDistributorTestCase(td.WriteDistributorTestCase):

    async def asyncSetUp(self):
        self.session_pool = await self._make_session_pool()
        self.store = PgWriteDistributor()
        self.store.provider_name = 'test.pg_write_distributor'

    async def asyncTearDown(self):
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await self.store.cleanup(ts_session)
        await self.session_pool._pool.close()
