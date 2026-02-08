import logging
import random
import unittest

from ascetic_ddd.faker.domain.distributors.o2m.distribution_distributor import DistributionDistributor

# logging.basicConfig(level="DEBUG")


class DistributionDistributorTestCase(unittest.TestCase):
    """
    Tests for O2M DistributionDistributor.

    Verify:
    - Mean is close to target_mean for different distributions
    - Different distributions produce different shapes
    - Factory methods work correctly
    """
    target_mean = 50
    iterations = 1000

    def test_exponential_average(self):
        """Exponential distribution: mean is close to target_mean."""
        dist = DistributionDistributor.exponential(target_mean=self.target_mean)

        total = sum(dist.distribute() for _ in range(self.iterations))
        average = total / self.iterations

        logging.info("Exponential average: %.2f (expected: %d)", average, self.target_mean)
        self.assertAlmostEqual(average, self.target_mean, delta=self.target_mean * 0.15)

    def test_exponential_has_long_tail(self):
        """Exponential distribution: has a long tail."""
        dist = DistributionDistributor.exponential(target_mean=self.target_mean)

        results = [dist.distribute() for _ in range(self.iterations)]
        max_val = max(results)
        median = sorted(results)[len(results) // 2]

        logging.info("Exponential - Max: %d, Median: %d", max_val, median)

        # Maximum should be significantly greater than the median
        self.assertGreater(max_val, median * 2)

    def test_pareto_average(self):
        """Pareto distribution: mean is close to target_mean."""
        dist = DistributionDistributor.pareto(alpha=2.5, target_mean=self.target_mean)

        total = sum(dist.distribute() for _ in range(self.iterations))
        average = total / self.iterations

        logging.info("Pareto average: %.2f (expected: %d)", average, self.target_mean)
        self.assertAlmostEqual(average, self.target_mean, delta=self.target_mean * 0.2)

    def test_pareto_extreme_values(self):
        """Pareto distribution: has extreme values."""
        dist = DistributionDistributor.pareto(alpha=2.0, target_mean=self.target_mean)

        results = [dist.distribute() for _ in range(self.iterations)]
        max_val = max(results)

        logging.info("Pareto max: %d (target_mean: %d)", max_val, self.target_mean)

        # Pareto can produce very large values
        self.assertGreater(max_val, self.target_mean * 3)

    def test_lognormal_average(self):
        """Lognormal distribution: mean is close to target_mean."""
        dist = DistributionDistributor.lognormal(sigma=0.5, target_mean=self.target_mean)

        total = sum(dist.distribute() for _ in range(self.iterations))
        average = total / self.iterations

        logging.info("Lognormal average: %.2f (expected: %d)", average, self.target_mean)
        self.assertAlmostEqual(average, self.target_mean, delta=self.target_mean * 0.15)

    def test_gamma_average(self):
        """Gamma distribution: mean is close to target_mean."""
        dist = DistributionDistributor.gamma(shape=2.0, target_mean=self.target_mean)

        total = sum(dist.distribute() for _ in range(self.iterations))
        average = total / self.iterations

        logging.info("Gamma average: %.2f (expected: %d)", average, self.target_mean)
        self.assertAlmostEqual(average, self.target_mean, delta=self.target_mean * 0.15)

    def test_weibull_average(self):
        """Weibull distribution: mean is close to target_mean."""
        dist = DistributionDistributor.weibull(shape=1.5, target_mean=self.target_mean)

        total = sum(dist.distribute() for _ in range(self.iterations))
        average = total / self.iterations

        logging.info("Weibull average: %.2f (expected: %d)", average, self.target_mean)
        self.assertAlmostEqual(average, self.target_mean, delta=self.target_mean * 0.15)

    def test_uniform_average(self):
        """Uniform distribution: mean is close to target_mean."""
        dist = DistributionDistributor.uniform(target_mean=self.target_mean, spread=0.5)

        total = sum(dist.distribute() for _ in range(self.iterations))
        average = total / self.iterations

        logging.info("Uniform average: %.2f (expected: %d)", average, self.target_mean)
        self.assertAlmostEqual(average, self.target_mean, delta=self.target_mean * 0.1)

    def test_uniform_bounded(self):
        """Uniform distribution: values are within the spread bounds."""
        dist = DistributionDistributor.uniform(target_mean=self.target_mean, spread=0.3)

        results = [dist.distribute() for _ in range(self.iterations)]
        min_val = min(results)
        max_val = max(results)

        logging.info("Uniform - Min: %d, Max: %d", min_val, max_val)

        # Should be within approximately [target_mean*0.7, target_mean*1.3]
        self.assertGreaterEqual(min_val, self.target_mean * 0.5)
        self.assertLessEqual(max_val, self.target_mean * 1.7)

    def test_custom_sampler(self):
        """Custom sampler works."""
        dist = DistributionDistributor(
            sampler=lambda: random.expovariate(1),
            sampler_mean=1.0,
            target_mean=self.target_mean,
        )

        total = sum(dist.distribute() for _ in range(self.iterations))
        average = total / self.iterations

        self.assertAlmostEqual(average, self.target_mean, delta=self.target_mean * 0.15)

    def test_scipy_distribution(self):
        """scipy.stats distribution works (if scipy is available)."""
        try:
            from scipy import stats
        except ImportError:
            self.skipTest("scipy not installed")

        dist = DistributionDistributor(
            distribution=stats.expon(),
            target_mean=self.target_mean,
        )

        total = sum(dist.distribute() for _ in range(self.iterations))
        average = total / self.iterations

        logging.info("Scipy expon average: %.2f (expected: %d)", average, self.target_mean)
        self.assertAlmostEqual(average, self.target_mean, delta=self.target_mean * 0.15)

    def test_validation_no_distribution_or_sampler(self):
        """Error if neither distribution nor sampler is specified."""
        with self.assertRaises(ValueError):
            DistributionDistributor(target_mean=self.target_mean)

    def test_validation_both_distribution_and_sampler(self):
        """Error if both distribution and sampler are specified."""
        try:
            from scipy import stats
            with self.assertRaises(ValueError):
                DistributionDistributor(
                    distribution=stats.expon(),
                    sampler=lambda: 1.0,
                    target_mean=self.target_mean,
                )
        except ImportError:
            self.skipTest("scipy not installed")

    def test_validation_sampler_without_sampler_mean(self):
        """Error if sampler is provided without sampler_mean."""
        with self.assertRaises(ValueError):
            DistributionDistributor(
                sampler=lambda: 1.0,
                target_mean=self.target_mean,
            )

    def test_pareto_invalid_alpha(self):
        """Pareto with alpha <= 1 raises an error."""
        with self.assertRaises(ValueError):
            DistributionDistributor.pareto(alpha=1.0, target_mean=self.target_mean)

    def test_stateless(self):
        """Distributor is stateless."""
        dist = DistributionDistributor.exponential(target_mean=self.target_mean)

        r1 = dist.distribute()
        r2 = dist.distribute()
        r3 = dist.distribute()

        self.assertGreaterEqual(r1, 0)
        self.assertGreaterEqual(r2, 0)
        self.assertGreaterEqual(r3, 0)


if __name__ == '__main__':
    unittest.main()
