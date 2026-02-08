import logging
import unittest

from ascetic_ddd.faker.domain.distributors.o2m.skew_distributor import SkewDistributor

# logging.basicConfig(level="DEBUG")


class SkewDistributorTestCase(unittest.TestCase):
    """
    Tests for O2M SkewDistributor.

    Verify:
    - Average number of items is close to mean
    - With skew>1, the distribution is non-uniform (there are large and small values)
    """
    mean = 50
    iterations = 1000

    def test_average_equals_mean(self):
        """Average number of items should be close to mean."""
        dist = SkewDistributor(skew=2.0, mean=self.mean)

        total = sum(dist.distribute() for _ in range(self.iterations))
        average = total / self.iterations

        logging.info("Average: %.2f (expected: %d)", average, self.mean)
        self.assertAlmostEqual(average, self.mean, delta=self.mean * 0.15)

    def test_uniform_distribution_skew_1(self):
        """With skew=1.0, all receive approximately the same amount."""
        dist = SkewDistributor(skew=1.0, mean=self.mean)

        results = [dist.distribute() for _ in range(self.iterations)]
        average = sum(results) / len(results)

        # All results should be around mean
        self.assertAlmostEqual(average, self.mean, delta=self.mean * 0.15)

    def test_skewed_distribution_has_variance(self):
        """With skew>1, there should be significant variance."""
        dist = SkewDistributor(skew=3.0, mean=self.mean)

        results = [dist.distribute() for _ in range(self.iterations)]

        min_val = min(results)
        max_val = max(results)

        logging.info("Min: %d, Max: %d, Ratio: %.1f", min_val, max_val, max_val / max(min_val, 1))

        # There should be a significant difference between min and max
        self.assertGreater(max_val, min_val * 3)

    def test_high_skew_extreme_values(self):
        """With high skew, very large values are possible."""
        dist = SkewDistributor(skew=3.0, mean=self.mean)

        results = [dist.distribute() for _ in range(self.iterations)]
        max_val = max(results)

        logging.info("Max value with skew=3.0: %d", max_val)

        # Maximum should be significantly greater than the average
        self.assertGreater(max_val, self.mean * 2)

    def test_stateless(self):
        """Distributor is stateless -- can be called from different threads."""
        dist = SkewDistributor(skew=2.0, mean=self.mean)

        # Multiple calls
        r1 = dist.distribute()
        r2 = dist.distribute()
        r3 = dist.distribute()

        # All should return valid values
        self.assertGreaterEqual(r1, 0)
        self.assertGreaterEqual(r2, 0)
        self.assertGreaterEqual(r3, 0)


if __name__ == '__main__':
    unittest.main()
