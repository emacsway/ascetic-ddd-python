import random
import typing
from typing import Callable, Protocol, runtime_checkable

from ascetic_ddd.faker.domain.distributors.o2m.interfaces import IO2MDistributor

__all__ = ('DistributionDistributor',)


@runtime_checkable
class ScipyDistribution(Protocol):
    """Protocol for scipy.stats distributions."""
    def rvs(self, size: int | None = None) -> float: ...
    def mean(self) -> float: ...


class DistributionDistributor(IO2MDistributor):
    """
    Universal O2M distributor with an arbitrary statistical distribution.

    Accepts a distribution as a strategy:
    - scipy.stats distribution (recommended)
    - callable (generator function)

    Examples of scipy.stats distributions:
    - stats.expon() -- exponential (many small, few large)
    - stats.pareto(b=2.0) -- Pareto (80/20 rule)
    - stats.lognorm(s=1.0) -- log-normal (company sizes, incomes)
    - stats.gamma(a=2.0) -- gamma
    - stats.weibull_min(c=1.5) -- Weibull
    - stats.zipf(a=2.0) -- Zipf (frequencies, popularity)

    Examples:
        from scipy import stats

        # Exponential distribution
        dist = DistributionDistributor(
            distribution=stats.expon(),
            target_mean=50,
        )

        # Pareto (80/20)
        dist = DistributionDistributor(
            distribution=stats.pareto(b=2.0),
            target_mean=50,
        )

        # With callable
        dist = DistributionDistributor(
            sampler=lambda: random.expovariate(1),
            sampler_mean=1.0,
            target_mean=50,
        )

        devices_count = dist.distribute()  # mean = 50
    """
    _distribution: ScipyDistribution | None
    _sampler: Callable[[], float] | None
    _sampler_mean: float | None
    _target_mean: float

    def __init__(
            self,
            distribution: ScipyDistribution | None = None,
            sampler: Callable[[], float] | None = None,
            sampler_mean: float | None = None,
            target_mean: float | None = None,
    ):
        """
        Args:
            distribution: scipy.stats distribution object (e.g. stats.expon())
            sampler: Callable returning a random value (alternative to distribution)
            sampler_mean: Mean value of the sampler (required if sampler is used)
            target_mean: Target mean number of items per owner
        """
        if distribution is None and sampler is None:
            raise ValueError("Either distribution or sampler must be specified")

        if distribution is not None and sampler is not None:
            raise ValueError("Specify only distribution or sampler, not both")

        if sampler is not None and sampler_mean is None:
            raise ValueError("sampler_mean must be specified when using sampler")

        self._distribution = distribution
        self._sampler = sampler
        self._sampler_mean = sampler_mean
        self._target_mean = target_mean if target_mean is not None else 50.0

        # Compute the distribution mean for normalization
        if self._distribution is not None:
            try:
                self._dist_mean = float(self._distribution.mean())
            except (TypeError, ValueError):
                # Some distributions do not have a finite mean
                self._dist_mean = 1.0
        else:
            self._dist_mean = self._sampler_mean if self._sampler_mean else 1.0

    def distribute(self) -> int:
        """
        Returns the number of items from the distribution.

        Returns:
            Random number of items. Average across all calls = target_mean.
        """
        # Generate a value from the distribution
        if self._distribution is not None:
            raw_value = float(self._distribution.rvs())
        else:
            assert self._sampler is not None
            raw_value = self._sampler()

        # Normalize: raw_value / dist_mean * target_mean
        if self._dist_mean > 0:
            normalized = raw_value / self._dist_mean * self._target_mean
        else:
            normalized = raw_value

        # Return a non-negative integer
        return max(0, round(normalized))

    @classmethod
    def exponential(cls, target_mean: float = 50.0) -> 'DistributionDistributor':
        """
        Creates a distributor with exponential distribution.

        Many small values, few large ones. Mean = target_mean.
        """
        return cls(
            sampler=lambda: random.expovariate(1),
            sampler_mean=1.0,
            target_mean=target_mean,
        )

    @classmethod
    def pareto(cls, alpha: float = 2.0, target_mean: float = 50.0) -> 'DistributionDistributor':
        """
        Creates a distributor with Pareto distribution.

        The 80/20 rule. alpha determines the degree of inequality:
        - alpha=1.16: 80% of items belong to 20% of owners
        - alpha=2.0: moderate inequality
        - alpha>3: more uniform

        Args:
            alpha: Shape parameter (larger = more uniform)
            target_mean: Target mean
        """
        if alpha <= 1:
            raise ValueError("alpha must be > 1 for a finite mean")

        # Pareto mean = alpha / (alpha - 1) for x_m = 1
        pareto_mean = alpha / (alpha - 1)

        return cls(
            sampler=lambda: random.paretovariate(alpha),
            sampler_mean=pareto_mean,
            target_mean=target_mean,
        )

    @classmethod
    def lognormal(cls, sigma: float = 1.0, target_mean: float = 50.0) -> 'DistributionDistributor':
        """
        Creates a distributor with log-normal distribution.

        Models company sizes, incomes, etc. well.

        Args:
            sigma: Shape parameter (larger = more spread)
            target_mean: Target mean
        """
        import math
        # For lognormal(0, sigma): mean = exp(sigma^2 / 2)
        lognorm_mean = math.exp(sigma ** 2 / 2)

        return cls(
            sampler=lambda: random.lognormvariate(0, sigma),
            sampler_mean=lognorm_mean,
            target_mean=target_mean,
        )

    @classmethod
    def gamma(cls, shape: float = 2.0, target_mean: float = 50.0) -> 'DistributionDistributor':
        """
        Creates a distributor with gamma distribution.

        Args:
            shape: Shape parameter (k or alpha)
            target_mean: Target mean
        """
        # Gamma mean = shape * theta, using theta=1
        gamma_mean = shape

        return cls(
            sampler=lambda: random.gammavariate(shape, 1.0),
            sampler_mean=gamma_mean,
            target_mean=target_mean,
        )

    @classmethod
    def weibull(cls, shape: float = 1.5, target_mean: float = 50.0) -> 'DistributionDistributor':
        """
        Creates a distributor with Weibull distribution.

        Args:
            shape: Shape parameter (k)
            target_mean: Target mean
        """
        import math
        # Weibull mean = lambda * Gamma(1 + 1/k), using lambda=1
        weibull_mean = math.gamma(1 + 1 / shape)

        return cls(
            sampler=lambda: random.weibullvariate(1.0, shape),
            sampler_mean=weibull_mean,
            target_mean=target_mean,
        )

    @classmethod
    def uniform(cls, target_mean: float = 50.0, spread: float = 0.5) -> 'DistributionDistributor':
        """
        Creates a distributor with uniform distribution.

        Args:
            target_mean: Target mean
            spread: Spread (0.5 = from 0.5*target_mean to 1.5*target_mean)
        """
        low = target_mean * (1 - spread)
        high = target_mean * (1 + spread)
        uniform_mean = (low + high) / 2

        return cls(
            sampler=lambda: random.uniform(low, high),
            sampler_mean=uniform_mean,
            target_mean=target_mean,
        )
