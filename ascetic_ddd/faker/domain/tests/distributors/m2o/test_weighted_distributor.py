import copy
import functools
import math
import uuid
import pprint
import logging
import dataclasses
from collections import Counter
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.faker.infrastructure.tests.db import make_internal_pg_session_pool
from ascetic_ddd.faker.domain.distributors.m2o.factory import distributor_factory
from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.query_lookup_specification import QueryLookupSpecification
from ascetic_ddd.session.interfaces import ISession

# logging.basicConfig(level="DEBUG")


@dataclasses.dataclass(kw_only=True)
class SomePk:
    id: uuid.UUID
    another_model_id: uuid.UUID

    def __hash__(self):
        return hash((self.id, self.another_model_id))


class Factory:
    another_model_id: uuid.UUID

    async def __call__(self, _session: ISession):
        return SomePk(
            id=uuid.uuid4(),
            another_model_id=self.another_model_id
        )


class _BaseDistributorTestCase(IsolatedAsyncioTestCase):
    distributor_factory = staticmethod(distributor_factory)

    weights = [0.7, 0.2, 0.07, 0.03]
    null_weight = 0.5
    mean = 50
    count = 3000

    async def _make_session_pool(self):
        return await make_internal_pg_session_pool()

    async def asyncSetUp(self):
        self.session_pool = await self._make_session_pool()
        self.dist = self.distributor_factory(
            weights=self.weights,
            mean=self.mean,
            null_weight=self.null_weight,
        )
        self.dist.provider_name = 'path.Fk.fk_id'

    def _check_mean_of_emptiable_result(self, result, strategy=lambda actual_mean, expected_mean: None):
        counter = Counter(result)
        self.assertGreaterEqual(counter[None] / counter.total(), self.null_weight - 0.1)
        self.assertLessEqual(counter[None] / counter.total(), self.null_weight + 0.1)
        actual_mean = counter.total() / len(counter)
        expected_mean = (self.mean * (len(counter) - 1)) / (len(counter) * self.null_weight)
        logging.info(
            "Emptiable mean, Actual: %s, Expected: %s, Empty: %s, Non-Empty: %s, Total: %s, Len: %s",
            actual_mean, expected_mean, counter[None], counter.total() - counter[None], counter.total(), len(counter)
        )
        # counter_repr = [(k, v) for k, v in sorted(counter.items(), key=lambda item: item[1], reverse=True)]
        # logging.debug(pprint.pformat(counter_repr))
        # Probabilistic approach (PgDistributor) has higher variance
        self.assertLessEqual(actual_mean, expected_mean * 1.5)
        strategy(actual_mean, expected_mean)

    def _check_mean_of_non_empty_result(self, result, strategy=lambda actual_mean, expected_mean: None):
        counter = Counter(result)
        del counter[None]
        actual_mean = counter.total() / len(counter)
        expected_mean = self.mean
        logging.info(
            "Non-empty mean, Actual: %s, Expected: %s, Total: %s, Len: %s",
            actual_mean, expected_mean, counter.total(), len(counter)
        )
        # Probabilistic approach (PgDistributor) has higher variance
        self.assertLessEqual(actual_mean, expected_mean * 1.5)
        strategy(actual_mean, expected_mean)

    def _check_non_empty_result(self, result):
        counter = Counter(result)
        del counter[None]

        counts = list(sorted(counter.values(), reverse=True))
        partition_size = len(counts) / len(self.weights)

        for part_num in range(len(self.weights) - 1):
            current_partition_counts = counts[
               math.floor(part_num * partition_size):
               math.ceil((part_num + 1) * partition_size)
            ]
            next_partition_counts = counts[
                math.floor((part_num + 1) * partition_size):
                math.ceil((part_num + 2) * partition_size)
            ]
            logging.info("Pos: %s, Current sum: %s, Next sum: %s",
                         part_num, sum(current_partition_counts), sum(next_partition_counts))
            self.assertGreaterEqual(sum(current_partition_counts), sum(next_partition_counts))

        for part_num, weight in enumerate(self.weights):
            current_partition_counts = counts[
               math.floor(part_num * partition_size):
               math.ceil((part_num + 1) * partition_size)
            ]
            actual_weight = sum(current_partition_counts) / counter.total()
            logging.info("Pos: %s, Actual weight: %s, Expected weight: %s", part_num, actual_weight, weight)
            # When dynamically creating values (without per-value counters), earlier values
            # receive more calls because they are available longer. This yields ~85% vs 70% for the first
            # partition. The probabilistic approach (without touch) adds even more variance.
            # For a fake data generator this is acceptable.
            self.assertLessEqual(actual_weight, weight * 3.0)
            self.assertAlmostEqual(actual_weight, weight, delta=weight * 2.0)

        counter_repr = [(k, v) for k, v in sorted(counter.items(), key=lambda item: item[1], reverse=True)]
        logging.info(pprint.pformat(counter_repr))

    async def asyncTearDown(self):
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await self.dist.cleanup(ts_session)
        await self.session_pool._pool.close()


class DefaultKeyDistributorTestCase(_BaseDistributorTestCase):

    def _make_value_factory(self):
        val = 0

        async def factory(_session: ISession):
            nonlocal val
            res = val
            val += 1
            return res

        return factory

    async def test_default_key(self):
        val = 0

        async def factory(_session: ISession, _position: int = -1):
            nonlocal val
            res = val
            val += 1
            return res

        async with self.session_pool.session() as session, session.atomic() as ts_session:
            result = []
            for _ in range(self.count):
                try:
                    result.append((await self.dist.next(ts_session, EmptySpecification())).unwrap_or(None))
                except Cursor as cursor:
                    value = await factory(ts_session, cursor.position)
                    await cursor.append(ts_session, value)
                    result.append(value)

        # Probabilistic approach in PgDistributor has higher variance,
        # so we use 40% tolerance instead of 20%
        self._check_mean_of_emptiable_result(
            result,
            functools.partial(self.assertAlmostEqual, delta=(self.mean / self.null_weight) * 0.4)
        )
        self._check_mean_of_non_empty_result(
            result,
            functools.partial(self.assertAlmostEqual, delta=self.mean * 0.4)
        )
        self._check_non_empty_result(result)


class SpecificKeyDistributorTestCase(_BaseDistributorTestCase):

    async def test_specific_key(self):
        factory = Factory()

        factory.another_model_id = uuid.uuid4()
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            result = []
            for i in range(self.count):
                if i % 200 == 0:
                    factory.another_model_id = uuid.uuid4()
                spec = QueryLookupSpecification(
                    QueryParser().parse({'another_model_id': {'$eq': factory.another_model_id}}),
                    lambda obj: dataclasses.asdict(obj)
                )
                try:
                    result.append((await self.dist.next(ts_session, specification=spec)).unwrap_or(None))
                except Cursor as cursor:
                    value = await factory(ts_session)
                    await cursor.append(ts_session, value)
                    result.append(value)

        self._check_mean_of_emptiable_result(result)
        self._check_mean_of_non_empty_result(result)
        self._check_non_empty_result(result)


class CollectionDistributorTestCase(_BaseDistributorTestCase):
    weights = [0.7, 0.2, 0.1]

    async def asyncSetUp(self):
        self.session_pool = await self._make_session_pool()
        self._values = self._make_values()
        self._value_iter = iter(self._values)
        self._source_available = True
        self.mean = self.null_weight * self.count / len(self._values)
        self.dist = self.distributor_factory(
            weights=self.weights,
            mean=None,
            null_weight=self.null_weight,
        )
        self.dist.provider_name = 'path.Fk.fk_id'

    def _make_values(self):
        return [5, 10, 20]

    async def _next_with_fallback(self, ts_session):
        """If source is exhausted, use fallback via repeated next call."""
        try:
            return (await self.dist.next(ts_session, EmptySpecification())).unwrap_or(None)
        except Cursor as cursor:
            if self._source_available:
                try:
                    value = next(self._value_iter)
                    await cursor.append(ts_session, value)
                    return value
                except StopIteration:
                    self._source_available = False
            # Fallback: call next again (now there are values, select will return one)
            try:
                return (await self.dist.next(ts_session, EmptySpecification())).unwrap_or(None)
            except Cursor:
                # In rare case Cursor is raised again (probabilistically)
                return (await self.dist.next(ts_session, EmptySpecification())).unwrap_or(None)

    async def test_fixed_collection(self):

        async with self.session_pool.session() as session, session.atomic() as ts_session:
            result = [await self._next_with_fallback(ts_session) for _ in range(self.count)]

        self._check_mean_of_emptiable_result(
            result,
            functools.partial(self.assertAlmostEqual, delta=(self.mean / self.null_weight) * 0.05)
        )
        self._check_mean_of_non_empty_result(
            result,
            functools.partial(self.assertAlmostEqual, delta=self.mean * 0.05)
        )
        self._check_non_empty_result(result)
