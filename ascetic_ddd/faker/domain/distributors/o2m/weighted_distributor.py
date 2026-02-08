import math
import random
import typing

from ascetic_ddd.faker.domain.distributors.o2m.interfaces import IO2MDistributor

__all__ = ('WeightedDistributor',)


class WeightedDistributor(IO2MDistributor):
    """
    O2M distributor with weighted distribution across partitions.

    Parameters:
    - weights: partition weights (e.g. [0.7, 0.2, 0.07, 0.03])
    - mean: average number of items per owner

    Example: weights=[0.7, 0.2, 0.07, 0.03], mean=50
    - 25% of calls fall into partition 0 (large) -- receive more than mean
    - 25% of calls fall into partition 3 (small) -- receive less than mean
    - Average across all calls = mean

    Example:
        dist = WeightedDistributor(weights=[0.7, 0.2, 0.07, 0.03], mean=50)
        devices_count = dist.distribute()  # mean = 50
    """
    _weights: list[float]
    _mean: float

    def __init__(
            self,
            weights: typing.Iterable[float] = tuple(),
            mean: float | None = None,
    ):
        self._weights = list(weights) if weights else [0.7, 0.2, 0.07, 0.03]
        if not self._weights:
            self._weights = [1.0]
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
        num_partitions = len(self._weights)

        # Normalize weights
        total_weight = sum(self._weights)
        if total_weight == 0:
            return self._mean

        # Partition size (fraction of positions)
        partition_size = 1.0 / num_partitions

        # Determine the partition by position
        partition_idx = min(int(position / partition_size), num_partitions - 1)

        # Position within the partition [0, 1)
        local_position = (position - partition_idx * partition_size) / partition_size

        # Partition weight (fraction of items)
        partition_weight = self._weights[partition_idx] / total_weight

        # Mean for this partition = mean * partition_weight * num_partitions
        # (since the partition contains 1/num_partitions positions but receives partition_weight items)
        average_in_partition = self._mean * partition_weight * num_partitions

        # Local skew within the partition (as in M2O)
        if partition_idx > 0 and self._weights[partition_idx] > 0:
            ratio = self._weights[partition_idx - 1] / self._weights[partition_idx]
            local_skew = max(1.0, math.log2(ratio) + 1)
        else:
            local_skew = 1.0

        # When local_skew=1: uniform distribution within the partition
        if local_skew <= 1.01:
            return average_in_partition

        # Power-law distribution within the partition
        individual_weight = (1 - local_position) ** local_skew
        average_weight = 1.0 / (local_skew + 1)

        return average_in_partition * individual_weight / average_weight

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
