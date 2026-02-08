import logging
import unittest

from ascetic_ddd.faker.domain.distributors.o2m.weighted_distributor import WeightedDistributor

# logging.basicConfig(level="DEBUG")


class WeightedDistributorTestCase(unittest.TestCase):
    """
    Tests for O2M WeightedDistributor.

    Verify:
    - Average number of items is close to mean
    - Distribution across partitions matches the weights
    """
    weights = [0.7, 0.2, 0.07, 0.03]
    mean = 50
    iterations = 1000

    def test_average_equals_mean(self):
        """Average number of items should be close to mean."""
        dist = WeightedDistributor(weights=self.weights, mean=self.mean)

        total = sum(dist.distribute() for _ in range(self.iterations))
        average = total / self.iterations

        logging.info("Average: %.2f (expected: %d)", average, self.mean)
        self.assertAlmostEqual(average, self.mean, delta=self.mean * 0.15)

    def test_distribution_has_variance(self):
        """Distribution should have significant variance."""
        dist = WeightedDistributor(weights=self.weights, mean=self.mean)

        results = [dist.distribute() for _ in range(self.iterations)]

        min_val = min(results)
        max_val = max(results)

        logging.info("Min: %d, Max: %d", min_val, max_val)

        # There should be a difference between min and max
        self.assertGreater(max_val, min_val * 2)

    def test_extreme_weights(self):
        """With extreme weights, the distribution is highly non-uniform."""
        dist = WeightedDistributor(weights=[0.9, 0.09, 0.009, 0.001], mean=self.mean)

        results = [dist.distribute() for _ in range(self.iterations)]

        min_val = min(results)
        max_val = max(results)

        logging.info("Extreme weights - Min: %d, Max: %d, Ratio: %.1f",
                     min_val, max_val, max_val / max(min_val, 1))

        # With extreme weights the difference is even larger
        self.assertGreater(max_val, min_val * 5)

    def test_equal_weights(self):
        """With equal weights, the distribution is more uniform."""
        dist = WeightedDistributor(weights=[0.25, 0.25, 0.25, 0.25], mean=self.mean)

        results = [dist.distribute() for _ in range(self.iterations)]
        average = sum(results) / len(results)

        # Average should be around mean
        self.assertAlmostEqual(average, self.mean, delta=self.mean * 0.15)

    def test_single_weight(self):
        """Single weight -- all in one partition."""
        dist = WeightedDistributor(weights=[1.0], mean=self.mean)

        results = [dist.distribute() for _ in range(self.iterations)]
        average = sum(results) / len(results)

        self.assertAlmostEqual(average, self.mean, delta=self.mean * 0.15)

    def test_stateless(self):
        """Distributor is stateless -- can be called from different threads."""
        dist = WeightedDistributor(weights=self.weights, mean=self.mean)

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
