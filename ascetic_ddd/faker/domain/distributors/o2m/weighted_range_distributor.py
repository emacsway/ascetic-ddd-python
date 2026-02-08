import random
import typing

from ascetic_ddd.faker.domain.distributors.o2m.interfaces import IO2MDistributor

__all__ = ('WeightedRangeDistributor',)


class WeightedRangeDistributor(IO2MDistributor):
    """
    O2M distributor for selecting an integer from a bounded range.

    Unlike WeightedDistributor (which returns a count around mean),
    this distributor returns a value strictly from the range [min_val, max_val].

    Parameters:
    - min_val: minimum value (inclusive)
    - max_val: maximum value (inclusive)
    - weights: weights for each value in the range (optional)

    Examples:
        # Uniform distribution [0, 5]
        dist = WeightedRangeDistributor(0, 5)
        value = dist.distribute()  # 0, 1, 2, 3, 4 or 5

        # Weighted: 0 more frequent, 5 less frequent
        dist = WeightedRangeDistributor(0, 5, weights=[0.5, 0.25, 0.12, 0.07, 0.04, 0.02])
        value = dist.distribute()

        # Weighted with fewer weights (interpolated across the full range)
        dist = WeightedRangeDistributor(0, 5, weights=[0.7, 0.2, 0.1])
        value = dist.distribute()  # 0-5, weights are interpolated
    """
    _min_val: int
    _max_val: int
    _weights: list[float]
    _cumulative: list[float]

    def __init__(
            self,
            min_val: int,
            max_val: int,
            weights: typing.Iterable[float] | None = None,
    ):
        if min_val > max_val:
            raise ValueError(f"min_val ({min_val}) must be <= max_val ({max_val})")

        self._min_val = min_val
        self._max_val = max_val
        range_size = max_val - min_val + 1

        if weights is not None:
            weights_list = list(weights)
            if len(weights_list) == range_size:
                self._weights = weights_list
            elif len(weights_list) > range_size:
                # Truncate if there are more weights than needed
                self._weights = weights_list[:range_size]
            else:
                # Interpolate weights across the full range
                self._weights = self._interpolate_weights(weights_list, range_size)
        else:
            # Uniform distribution
            self._weights = [1.0] * range_size

        # Normalize and compute cumulative for fast selection
        total = sum(self._weights)
        if total <= 0:
            raise ValueError("Sum of weights must be > 0")

        self._cumulative = []
        cumsum = 0.0
        for w in self._weights:
            cumsum += w / total
            self._cumulative.append(cumsum)

    @staticmethod
    def _interpolate_weights(weights: list[float], target_size: int) -> list[float]:
        """
        Linear interpolation of weights to the target size.

        Example: weights=[0.7, 0.2, 0.1], target_size=6
        Result: weights are evenly distributed across positions 0-5
        """
        if len(weights) < 2:
            return weights * target_size if weights else [1.0] * target_size

        result = []
        src_len = len(weights)
        for i in range(target_size):
            # Position in the source array (fractional)
            src_pos = i * (src_len - 1) / (target_size - 1)
            # Indices of neighboring weights
            left_idx = int(src_pos)
            right_idx = min(left_idx + 1, src_len - 1)
            # Fraction between neighbors
            frac = src_pos - left_idx
            # Linear interpolation
            interpolated = weights[left_idx] * (1 - frac) + weights[right_idx] * frac
            result.append(interpolated)

        return result

    def distribute(self) -> int:
        """
        Returns a random value from the range [min_val, max_val].

        Returns:
            An integer according to the weights.
        """
        r = random.random()

        # Binary search for O(log n)
        left, right = 0, len(self._cumulative) - 1
        while left < right:
            mid = (left + right) // 2
            if self._cumulative[mid] < r:
                left = mid + 1
            else:
                right = mid

        return self._min_val + left

    @classmethod
    def uniform(cls, min_val: int, max_val: int) -> 'WeightedRangeDistributor':
        """Uniform distribution."""
        return cls(min_val, max_val)

    @classmethod
    def linear_decay(cls, min_val: int, max_val: int) -> 'WeightedRangeDistributor':
        """Linearly decaying weights: earlier values are more frequent."""
        range_size = max_val - min_val + 1
        weights = [range_size - i for i in range(range_size)]
        return cls(min_val, max_val, weights=weights)

    @classmethod
    def exponential_decay(cls, min_val: int, max_val: int, decay: float = 0.5) -> 'WeightedRangeDistributor':
        """
        Exponentially decaying weights.

        Args:
            decay: decay coefficient (0 < decay < 1).
                   Smaller = faster decay.
        """
        if not 0 < decay < 1:
            raise ValueError("decay must be between 0 and 1")

        range_size = max_val - min_val + 1
        weights = [decay ** i for i in range(range_size)]
        return cls(min_val, max_val, weights=weights)

    @classmethod
    def pareto_like(cls, min_val: int, max_val: int, alpha: float = 2.0) -> 'WeightedRangeDistributor':
        """
        Pareto-like distribution: the 80/20 rule.

        Args:
            alpha: shape parameter (larger = more uniform)
        """
        range_size = max_val - min_val + 1
        # weight(i) ∝ (i+1)^(-alpha)
        weights = [(i + 1) ** (-alpha) for i in range(range_size)]
        return cls(min_val, max_val, weights=weights)
