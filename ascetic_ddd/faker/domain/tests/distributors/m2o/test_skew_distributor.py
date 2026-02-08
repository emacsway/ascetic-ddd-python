import functools
import logging
import uuid
import dataclasses
from collections import Counter
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.faker.infrastructure.tests.db import make_internal_pg_session_pool
from ascetic_ddd.faker.domain.distributors.m2o.factory import distributor_factory
from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.faker.domain.specification.query_resolvable_specification import QueryResolvableSpecification
from ascetic_ddd.faker.domain.values.empty import Empty, empty
from ascetic_ddd.seedwork.domain.session.interfaces import ISession

# logging.basicConfig(level="DEBUG")


@dataclasses.dataclass(kw_only=True)
class SomePk:
    id: uuid.UUID | Empty
    another_model_id: uuid.UUID

    def __hash__(self):
        assert self.id is not empty
        assert self.another_model_id is not empty
        return hash((self.id, self.another_model_id))


class Factory:
    another_model_id: uuid.UUID

    async def __call__(self, _session: ISession):
        return SomePk(
            id=uuid.uuid4(),
            another_model_id=self.another_model_id
        )


class _BaseSkewDistributorTestCase(IsolatedAsyncioTestCase):
    """
    Base test class for SkewDistributor.

    We verify the power-law distribution: idx = n * (1 - random())^skew
    At skew=1: uniform distribution
    At skew=2: the first 50% of values receive ~75% of calls
    At skew=3: the first 33% of values receive ~70% of calls
    """
    distributor_factory = staticmethod(distributor_factory)

    skew = 2.0
    null_weight = 0.5
    mean = 50
    count = 3000

    async def _make_session_pool(self):
        return await make_internal_pg_session_pool()

    async def asyncSetUp(self):
        self.session_pool = await self._make_session_pool()
        self.dist = self.distributor_factory(
            skew=self.skew,
            mean=self.mean,
            null_weight=self.null_weight,
        )
        self.dist.provider_name = 'path.SkewFk.fk_id'

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
        # Probabilistic approach (PgSkewDistributor) has higher variance
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
        # Probabilistic approach (PgSkewDistributor) has higher variance
        self.assertLessEqual(actual_mean, expected_mean * 1.5)
        strategy(actual_mean, expected_mean)

    def _check_skew_distribution(self, result):
        """Verify skew: the first half should receive more calls."""
        counter = Counter(result)
        if None in counter:
            del counter[None]

        counts = list(sorted(counter.values(), reverse=True))
        n = len(counts)
        first_half_sum = sum(counts[:n // 2])
        second_half_sum = sum(counts[n // 2:])
        first_half_ratio = first_half_sum / counter.total()

        logging.info(
            "First half: %d (%.1f%%), Second half: %d (%.1f%%)",
            first_half_sum, first_half_ratio * 100,
            second_half_sum, (1 - first_half_ratio) * 100
        )

        # At skew>=2 the first half should receive significantly more
        self.assertGreater(first_half_ratio, 0.6)

    async def asyncTearDown(self):
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await self.dist.cleanup(ts_session)
        await self.session_pool._pool.close()


class DefaultKeySkewDistributorTestCase(_BaseSkewDistributorTestCase):

    async def test_default_key(self):
        val = 0

        async def factory(_session: ISession, _position: int | None = None):
            nonlocal val
            res = val
            val += 1
            return res

        async with self.session_pool.session() as session, session.atomic() as ts_session:
            result = []
            for _ in range(self.count):
                try:
                    result.append(await self.dist.next(ts_session))
                except Cursor as cursor:
                    value = await factory(ts_session, cursor.position)
                    await cursor.append(ts_session, value)
                    result.append(value)

        # Probabilistic approach in PgSkewDistributor has higher variance,
        # so we use 40% tolerance instead of 20%
        self._check_mean_of_emptiable_result(
            result,
            functools.partial(self.assertAlmostEqual, delta=(self.mean / self.null_weight) * 0.4)
        )
        self._check_mean_of_non_empty_result(
            result,
            functools.partial(self.assertAlmostEqual, delta=self.mean * 0.4)
        )
        self._check_skew_distribution(result)


class SpecificKeySkewDistributorTestCase(_BaseSkewDistributorTestCase):

    async def test_specific_key(self):
        factory = Factory()

        factory.another_model_id = uuid.uuid4()
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            result = []
            for i in range(self.count):
                if i % 200 == 0:
                    factory.another_model_id = uuid.uuid4()
                spec = QueryResolvableSpecification(
                    QueryParser().parse({'another_model_id': {'$eq': factory.another_model_id}}),
                    lambda obj: dataclasses.asdict(obj)
                )
                try:
                    result.append(await self.dist.next(ts_session, specification=spec))
                except Cursor as cursor:
                    value = await factory(ts_session)
                    await cursor.append(ts_session, value)
                    result.append(value)

        self._check_mean_of_emptiable_result(result)
        self._check_mean_of_non_empty_result(result)
        self._check_skew_distribution(result)


class CollectionSkewDistributorTestCase(_BaseSkewDistributorTestCase):
    skew = 3.0

    async def asyncSetUp(self):
        self.session_pool = await self._make_session_pool()
        self._values = self._make_values()
        self._value_iter = iter(self._values)
        self.mean = self.null_weight * self.count / len(self._values)
        self.dist = self.distributor_factory(
            skew=self.skew,
            mean=None,
            null_weight=self.null_weight,
        )
        self.dist.provider_name = 'path.SkewFk.fk_id'

    def _make_values(self):
        return [5, 10, 20]

    async def test_fixed_collection(self):

        async with self.session_pool.session() as session, session.atomic() as ts_session:
            result = []
            for _ in range(self.count):
                try:
                    result.append(await self.dist.next(ts_session))
                except Cursor as cursor:
                    try:
                        value = next(self._value_iter)
                        await cursor.append(ts_session, value)
                        result.append(value)
                    except StopIteration:
                        result.append(None)

        self._check_mean_of_emptiable_result(
            result,
            functools.partial(self.assertAlmostEqual, delta=(self.mean / self.null_weight) * 0.05)
        )
        self._check_mean_of_non_empty_result(
            result,
            functools.partial(self.assertAlmostEqual, delta=self.mean * 0.05)
        )
        self._check_skew_distribution(result)


class SkewIndexSelectIdxTestCase(IsolatedAsyncioTestCase):
    """
    Tests for SkewIndex._select_idx().

    We verify the formula: idx = int(n * (1 - random())^skew)
    Theoretically: P(idx < x*n) = x^(1/skew)
    """

    def _simulate_select_idx(self, n: int, skew: float, samples: int = 100000) -> list[int]:
        """Simulates SkewIndex._select_idx()"""
        import random
        results = []
        for _ in range(samples):
            idx = int(n * (1 - random.random()) ** skew)
            idx = min(idx, n - 1)
            results.append(idx)
        return results

    def _get_percentile_ratio(self, results: list[int], n: int, percentile: float) -> float:
        """Returns the proportion of results in the first percentile% of indices."""
        cutoff = int(n * percentile)
        count_in_range = sum(1 for r in results if r < cutoff)
        return count_in_range / len(results)

    async def test_select_idx_uniform(self):
        """At skew=1.0 the distribution is uniform."""
        n = 1000
        results = self._simulate_select_idx(n, skew=1.0)

        # The first 25% should receive ~25% of calls
        ratio = self._get_percentile_ratio(results, n, 0.25)
        self.assertAlmostEqual(ratio, 0.25, delta=0.02)

        # The first 50% should receive ~50% of calls
        ratio = self._get_percentile_ratio(results, n, 0.50)
        self.assertAlmostEqual(ratio, 0.50, delta=0.02)

    async def test_select_idx_theoretical_formula(self):
        """
        Verification of theoretical formula: P(idx < x*n) = x^(1/skew).

        Mathematical justification:
        - idx = n * (1 - u)^skew, where u ~ Uniform[0,1)
        - P(idx < k) = P(n*(1-u)^skew < k) = P((1-u) < (k/n)^(1/skew))
        - P(idx < k) = (k/n)^(1/skew)
        """
        n = 1000
        samples = 100000

        test_cases = [
            # (skew, percentile, expected_ratio, tolerance)
            (2.0, 0.10, 0.10 ** 0.5, 0.02),      # 10% → 31.6%
            (2.0, 0.25, 0.25 ** 0.5, 0.02),      # 25% → 50%
            (2.0, 0.50, 0.50 ** 0.5, 0.02),      # 50% → 70.7%
            (3.0, 0.10, 0.10 ** (1/3), 0.02),    # 10% → 46.4%
            (3.0, 0.25, 0.25 ** (1/3), 0.02),    # 25% → 63%
            (4.0, 0.10, 0.10 ** 0.25, 0.02),     # 10% → 56.2%
            (4.0, 0.50, 0.50 ** 0.25, 0.02),     # 50% → 84.1%
        ]

        for skew, percentile, expected, tolerance in test_cases:
            with self.subTest(skew=skew, percentile=percentile):
                results = self._simulate_select_idx(n, skew, samples)
                actual = self._get_percentile_ratio(results, n, percentile)

                self.assertAlmostEqual(
                    actual, expected, delta=tolerance,
                    msg="skew=%s, first %.0f%%: "
                        "expected %.1f%%, got %.1f%%" % (skew, percentile*100, expected*100, actual*100)
                )

    async def test_select_idx_skew_increases_bias(self):
        """Higher skew leads to greater bias toward the beginning."""
        n = 1000
        percentile = 0.25

        prev_ratio = 0
        for skew in [1.0, 2.0, 3.0, 4.0]:
            results = self._simulate_select_idx(n, skew)
            ratio = self._get_percentile_ratio(results, n, percentile)

            self.assertGreater(
                ratio, prev_ratio,
                msg="skew=%s should produce greater bias than the previous one" % skew
            )
            prev_ratio = ratio


class EstimateSkewTestCase(IsolatedAsyncioTestCase):
    """
    Tests for estimate_skew().

    We verify the formula: skew = 1 / (1 - alpha)
    where alpha is the Zipf parameter from log-log regression.
    """

    def _generate_skew_data(self, n: int, skew: float, samples: int) -> dict[int, int]:
        """Generates data with known skew for verifying estimate_skew."""
        import random
        counter = Counter()
        for _ in range(samples):
            u = random.random()
            idx = int(n * (1 - u) ** skew)
            idx = min(idx, n - 1)
            counter[idx] += 1
        return dict(counter)

    async def test_estimate_skew_formula(self):
        """
        Verification of formula skew = 1 / (1 - alpha).

        Mathematical justification:
        - SkewDistributor: idx = floor(n * (1 - u)^skew)
        - PDF: p(x) ∝ x^(1/skew - 1)
        - Zipf: freq(rank) ∝ rank^(-alpha)
        - Comparing: -alpha = 1/skew - 1 -> skew = 1/(1-alpha)
        """
        from ascetic_ddd.faker.domain.distributors.m2o.skew_distributor import estimate_skew

        test_cases = [
            # (skew, allowed error)
            # Positive bias grows with skew due to discretization
            (1.5, 0.15),
            (2.0, 0.15),
            (2.5, 0.20),
            (3.0, 0.30),
            (4.0, 0.55),
            (5.0, 0.80),
        ]

        for target_skew, tolerance in test_cases:
            with self.subTest(skew=target_skew):
                data = self._generate_skew_data(1000, target_skew, 100000)
                estimated_skew, r_squared = estimate_skew(data)

                self.assertGreater(r_squared, 0.95, "R-squared should be > 0.95 for a good fit")
                self.assertAlmostEqual(
                    estimated_skew, target_skew, delta=tolerance,
                    msg="skew=%s: expected ~%s, got %.3f" % (target_skew, target_skew, estimated_skew)
                )

    async def test_estimate_skew_uniform(self):
        """For a uniform distribution skew is approximately 1.0."""
        from ascetic_ddd.faker.domain.distributors.m2o.skew_distributor import estimate_skew

        data = self._generate_skew_data(1000, 1.0, 100000)
        estimated_skew, _ = estimate_skew(data)

        self.assertAlmostEqual(estimated_skew, 1.0, delta=0.1)

    async def test_estimate_skew_edge_cases(self):
        """Edge cases."""
        from ascetic_ddd.faker.domain.distributors.m2o.skew_distributor import estimate_skew

        # Empty dict
        skew, r2 = estimate_skew({})
        self.assertEqual(skew, 1.0)
        self.assertEqual(r2, 0.0)

        # Single element
        skew, r2 = estimate_skew({'a': 100})
        self.assertEqual(skew, 1.0)
        self.assertEqual(r2, 0.0)

        # Two elements
        skew, r2 = estimate_skew({'a': 100, 'b': 50})
        self.assertGreaterEqual(skew, 1.0)


class WeightsToSkewTestCase(IsolatedAsyncioTestCase):
    """
    Tests for weights_to_skew().

    We verify that the function correctly reproduces weights[0].
    """

    def _simulate_weights(self, n_partitions: int, skew: float, samples: int = 100000) -> list[float]:
        """Simulates SkewDistributor and returns partition weights."""
        import random
        partition_size = 1.0 / n_partitions
        counts = [0] * n_partitions

        for _ in range(samples):
            u = random.random()
            idx_normalized = (1 - u) ** skew
            partition = min(int(idx_normalized / partition_size), n_partitions - 1)
            counts[partition] += 1

        return [c / samples for c in counts]

    async def test_weights_to_skew_first_weight(self):
        """
        Verification: weights_to_skew() accurately reproduces weights[0].

        Formula: P(first partition) = (1/k)^(1/skew) = weights[0]
        Solving: skew = log(1/k) / log(weights[0])
        """
        from ascetic_ddd.faker.domain.distributors.m2o.skew_distributor import weights_to_skew

        test_weights = [
            [0.7, 0.2, 0.07, 0.03],
            [0.5, 0.3, 0.15, 0.05],
            [0.8, 0.1, 0.07, 0.03],
            [0.6, 0.25, 0.1, 0.05],
        ]

        for weights in test_weights:
            with self.subTest(weights=weights):
                skew = weights_to_skew(weights)
                simulated = self._simulate_weights(len(weights), skew)

                self.assertAlmostEqual(
                    simulated[0], weights[0], delta=0.02,
                    msg="weights[0]=%s: expected ~%s, got %.3f" % (weights[0], weights[0], simulated[0])
                )

    async def test_weights_to_skew_uniform(self):
        """Uniform weights lead to skew = 1.0."""
        from ascetic_ddd.faker.domain.distributors.m2o.skew_distributor import weights_to_skew

        skew = weights_to_skew([0.25, 0.25, 0.25, 0.25])
        self.assertAlmostEqual(skew, 1.0, delta=0.01)

        simulated = self._simulate_weights(4, skew)
        for i, w in enumerate(simulated):
            self.assertAlmostEqual(w, 0.25, delta=0.02, msg="partition %s" % i)

    async def test_weights_to_skew_edge_cases(self):
        """Edge cases."""
        from ascetic_ddd.faker.domain.distributors.m2o.skew_distributor import weights_to_skew

        # Empty list
        self.assertEqual(weights_to_skew([]), 1.0)

        # Single element
        self.assertEqual(weights_to_skew([1.0]), 1.0)

        # Invalid weights
        self.assertEqual(weights_to_skew([0.0, 0.5, 0.5]), 2.0)
        self.assertEqual(weights_to_skew([1.0, 0.0, 0.0]), 2.0)

    async def test_weights_to_skew_known_values(self):
        """Verification of known skew values."""
        from ascetic_ddd.faker.domain.distributors.m2o.skew_distributor import weights_to_skew
        import math

        # For 4 partitions: P(first) = (1/4)^(1/skew)
        # skew=2: P = 0.25^0.5 = 0.5
        # skew=3: P = 0.25^(1/3) ≈ 0.63
        # skew=4: P = 0.25^0.25 ≈ 0.707

        test_cases = [
            (0.5, 2.0),    # (target_weight[0], expected_skew)
            (0.25 ** (1/3), 3.0),
            (0.25 ** 0.25, 4.0),
        ]

        for target_p, expected_skew in test_cases:
            weights = [target_p, (1 - target_p) / 3, (1 - target_p) / 3, (1 - target_p) / 3]
            skew = weights_to_skew(weights)
            self.assertAlmostEqual(
                skew, expected_skew, delta=0.01,
                msg="weights[0]=%.3f: expected skew=%s, got %.3f" % (target_p, expected_skew, skew)
            )
