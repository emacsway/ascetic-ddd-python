import logging
import unittest

from ascetic_ddd.faker.domain.distributors.o2m.weighted_range_distributor import WeightedRangeDistributor

# logging.basicConfig(level="DEBUG")


class WeightedRangeDistributorTestCase(unittest.TestCase):
    """
    Tests for O2M WeightedRangeDistributor.

    Verify:
    - Values are strictly within the range [min_val, max_val]
    - Distribution matches the weights
    - Factory methods work correctly
    """
    iterations = 10000

    def test_values_in_range(self):
        """All values are within the range [min_val, max_val]."""
        dist = WeightedRangeDistributor(0, 5)

        for _ in range(self.iterations):
            value = dist.distribute()
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 5)

    def test_uniform_distribution(self):
        """Uniform distribution: all values are approximately equally frequent."""
        dist = WeightedRangeDistributor(0, 5)
        counts = {i: 0 for i in range(6)}

        for _ in range(self.iterations):
            counts[dist.distribute()] += 1

        expected = self.iterations / 6
        for i, count in counts.items():
            logging.info("Value %d: %d (expected: %.0f)", i, count, expected)
            self.assertAlmostEqual(count, expected, delta=expected * 0.2)

    def test_weighted_distribution(self):
        """Weighted distribution matches the weights."""
        weights = [0.5, 0.3, 0.15, 0.05]
        dist = WeightedRangeDistributor(0, 3, weights=weights)
        counts = {i: 0 for i in range(4)}

        for _ in range(self.iterations):
            counts[dist.distribute()] += 1

        for i, w in enumerate(weights):
            expected = self.iterations * w
            logging.info("Value %d: %d (expected: %.0f)", i, counts[i], expected)
            self.assertAlmostEqual(counts[i], expected, delta=expected * 0.2)

    def test_weights_shorter_than_range_interpolation(self):
        """Weights shorter than range: interpolation over the entire range."""
        dist = WeightedRangeDistributor(0, 5, weights=[0.7, 0.2, 0.1])
        counts = {i: 0 for i in range(6)}

        for _ in range(self.iterations):
            counts[dist.distribute()] += 1

        logging.info("Interpolated weights counts: %s", counts)

        # All values should be selected
        for i in range(6):
            self.assertGreater(counts[i], 0, f"Value {i} should be selected")

        # Decreasing distribution: 0 is most frequent, 5 is least frequent
        self.assertGreater(counts[0], counts[5])

        # Monotonic decrease
        for i in range(5):
            self.assertGreaterEqual(
                counts[i], counts[i + 1] * 0.8,  # With tolerance for statistics
                f"Value {i} should be >= {i+1}"
            )

    def test_interpolate_weights_method(self):
        """Direct verification of the interpolation method."""
        # 3 weights -> 6 positions
        weights = [0.7, 0.2, 0.1]
        result = WeightedRangeDistributor._interpolate_weights(weights, 6)

        self.assertEqual(len(result), 6)
        # First and last should match the original values
        self.assertAlmostEqual(result[0], 0.7)
        self.assertAlmostEqual(result[5], 0.1)
        # Monotonic decrease
        for i in range(5):
            self.assertGreaterEqual(result[i], result[i + 1])

    def test_interpolate_single_weight(self):
        """Interpolation of a single weight: all positions are equal."""
        dist = WeightedRangeDistributor(0, 5, weights=[1.0])
        counts = {i: 0 for i in range(6)}

        for _ in range(self.iterations):
            counts[dist.distribute()] += 1

        # Uniform distribution
        expected = self.iterations / 6
        for i, count in counts.items():
            self.assertAlmostEqual(count, expected, delta=expected * 0.2)

    def test_single_value_range(self):
        """Range with a single value."""
        dist = WeightedRangeDistributor(5, 5)

        for _ in range(100):
            self.assertEqual(dist.distribute(), 5)

    def test_negative_range(self):
        """Negative values in the range."""
        dist = WeightedRangeDistributor(-3, 3)

        values = set()
        for _ in range(self.iterations):
            value = dist.distribute()
            self.assertGreaterEqual(value, -3)
            self.assertLessEqual(value, 3)
            values.add(value)

        # All values should be encountered
        self.assertEqual(values, {-3, -2, -1, 0, 1, 2, 3})

    def test_linear_decay(self):
        """Linear decay: earlier values are more frequent."""
        dist = WeightedRangeDistributor.linear_decay(0, 4)
        counts = {i: 0 for i in range(5)}

        for _ in range(self.iterations):
            counts[dist.distribute()] += 1

        logging.info("Linear decay counts: %s", counts)

        # Each subsequent value should be less frequent
        for i in range(4):
            self.assertGreater(counts[i], counts[i + 1])

    def test_exponential_decay(self):
        """Exponential decay: earlier values are significantly more frequent."""
        dist = WeightedRangeDistributor.exponential_decay(0, 4, decay=0.5)
        counts = {i: 0 for i in range(5)}

        for _ in range(self.iterations):
            counts[dist.distribute()] += 1

        logging.info("Exponential decay counts: %s", counts)

        # 0 should be significantly more frequent than 4
        self.assertGreater(counts[0], counts[4] * 5)

    def test_pareto_like(self):
        """Pareto-like: strong skew towards earlier values."""
        dist = WeightedRangeDistributor.pareto_like(0, 4, alpha=2.0)
        counts = {i: 0 for i in range(5)}

        for _ in range(self.iterations):
            counts[dist.distribute()] += 1

        logging.info("Pareto-like counts: %s", counts)

        # 0 should be significantly more frequent
        self.assertGreater(counts[0], counts[1])
        self.assertGreater(counts[1], counts[2])

    def test_validation_min_greater_than_max(self):
        """Error if min_val > max_val."""
        with self.assertRaises(ValueError):
            WeightedRangeDistributor(5, 0)

    def test_validation_zero_weights(self):
        """Error if sum of weights = 0."""
        with self.assertRaises(ValueError):
            WeightedRangeDistributor(0, 5, weights=[0, 0, 0])

    def test_validation_decay_out_of_range(self):
        """Error if decay is outside (0, 1)."""
        with self.assertRaises(ValueError):
            WeightedRangeDistributor.exponential_decay(0, 5, decay=0)
        with self.assertRaises(ValueError):
            WeightedRangeDistributor.exponential_decay(0, 5, decay=1)
        with self.assertRaises(ValueError):
            WeightedRangeDistributor.exponential_decay(0, 5, decay=1.5)


if __name__ == '__main__':
    unittest.main()
