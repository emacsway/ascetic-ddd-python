import random

from ascetic_ddd.faker.domain.distributors.o2m.interfaces import IO2MDistributor

__all__ = ('SkewDistributor',)


class SkewDistributor(IO2MDistributor):
    """
    O2M distributor with power-law distribution.

    Parameters:
    - skew: degree of skew (1.0 = uniform, 2.0+ = skewed)
    - mean: average number of items per owner

    skew = 1.0 -- all owners receive approximately the same (mean)
    skew = 2.0 -- some receive more, most receive less
    skew = 3.0 -- strong skew

    Example:
        dist = SkewDistributor(skew=2.0, mean=50)
        devices_count = dist.distribute()  # mean = 50
    """
    _skew: float
    _mean: float

    def __init__(
            self,
            skew: float = 2.0,
            mean: float | None = None,
    ):
        self._skew = max(1.0, skew)
        self._mean = mean if mean is not None else 50.0

    def distribute(self) -> int:
        """
        Returns the number of items.

        Returns:
            Random number of items (from Poisson distribution).
            Average across all calls = mean.
        """
        # Choose a random position in the distribution [0, 1)
        position = random.random()

        # Compute the expected count for this position
        expected = self._compute_expected_for_position(position)

        if expected <= 0:
            return 0

        return self._poisson(expected)

    def _compute_expected_for_position(self, position: float) -> float:
        """Computes the expected number of items for a position in the distribution."""
        # When skew is close to 1.0 -- uniform distribution
        if self._skew <= 1.01:
            return self._mean

        # Power-law distribution: earlier positions receive more
        # weight(pos) ∝ (1 - pos)^skew
        # Normalize so that the mean = mean

        # Weight for the current position
        individual_weight = (1 - position) ** self._skew

        # Average weight (integral of (1-x)^skew over x from 0 to 1)
        average_weight = 1.0 / (self._skew + 1)

        # Normalized expected
        return self._mean * individual_weight / average_weight

    @staticmethod
    def _poisson(lam: float) -> int:
        """Generates a random number from the Poisson distribution."""
        if lam > 30:
            result = random.gauss(lam, lam ** 0.5)
            return max(0, round(result))

        L = 2.718281828 ** (-lam)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= random.random()
        return k - 1
