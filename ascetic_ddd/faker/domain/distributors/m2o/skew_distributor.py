import math
import random
import typing

from ascetic_ddd.faker.domain.distributors.m2o import IM2ODistributor
from ascetic_ddd.faker.domain.distributors.m2o.weighted_distributor import BaseIndex, BaseDistributor
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification

__all__ = ('SkewDistributor', 'SkewIndex', 'estimate_skew', 'weights_to_skew')


def estimate_skew(usage_counts: dict[typing.Any, int], tail_cutoff: float = 0.9) -> tuple[float, float]:
    """
    Estimate the skew parameter from real usage data.

    Args:
        usage_counts: {value: count} — how many times each value was used
        tail_cutoff: fraction of data for analysis (discard the tail)

    Returns:
        (skew, r_squared) — parameter and goodness of fit (0-1)

    Example:
        >>> counts = {'a': 100, 'b': 50, 'c': 25, 'd': 12}
        >>> skew, r2 = estimate_skew(counts)
        >>> dist = SkewDistributor(skew=skew)
    """
    if len(usage_counts) < 2:
        return 1.0, 0.0

    # Rank by frequency (DESC)
    sorted_counts = sorted(usage_counts.values(), reverse=True)

    # Log-log data (skip zeros and the tail)
    cutoff_idx = int(len(sorted_counts) * tail_cutoff)
    log_rank = []
    log_freq = []
    for rank, freq in enumerate(sorted_counts[:cutoff_idx], start=1):
        if freq > 0:
            log_rank.append(math.log(rank))
            log_freq.append(math.log(freq))

    if len(log_rank) < 2:
        return 1.0, 0.0

    # Linear regression: log_freq = -alpha * log_rank + const
    n = len(log_rank)
    sum_x = sum(log_rank)
    sum_y = sum(log_freq)
    sum_xy = sum(x * y for x, y in zip(log_rank, log_freq))
    sum_x2 = sum(x * x for x in log_rank)
    sum_y2 = sum(y * y for y in log_freq)

    denom = n * sum_x2 - sum_x ** 2
    if denom == 0:
        return 1.0, 0.0

    # Slope (alpha) — negative for a decreasing distribution
    alpha = -(n * sum_xy - sum_x * sum_y) / denom

    # R² — goodness of fit
    ss_tot = sum_y2 - sum_y ** 2 / n
    if ss_tot == 0:
        r_squared = 0.0
    else:
        mean_y = sum_y / n
        ss_res = sum((y - (mean_y - alpha * (x - sum_x / n))) ** 2
                     for x, y in zip(log_rank, log_freq))
        r_squared = max(0, 1 - ss_res / ss_tot)

    # skew from alpha: skew = 1 / (1 - alpha)
    # Derivation: p(x) ∝ x^(1/skew - 1), Zipf: freq ∝ rank^(-alpha)
    # Comparing exponents: -alpha = 1/skew - 1 → skew = 1/(1-alpha)
    alpha = max(0, min(alpha, 0.9))  # clamp: alpha >= 0.9 → skew >= 10
    skew = 1.0 / (1.0 - alpha) if alpha < 1.0 else 10.0

    return skew, r_squared


def weights_to_skew(weights: list[float]) -> float:
    """
    Convert a list of weights to a skew parameter.

    For power-law distribution idx = n * (1-r)^skew:
    P(first quartile) = (1/len(weights))^(1/skew)

    We fit skew so that the first quartile ≈ weights[0].

    Args:
        weights: list of partition weights (e.g. [0.7, 0.2, 0.07, 0.03])

    Returns:
        skew: parameter for SkewDistributor

    Example:
        >>> skew = weights_to_skew([0.7, 0.2, 0.07, 0.03])
        >>> skew  # ≈ 3.89
    """
    if not weights or len(weights) < 2:
        return 1.0

    target_q1 = weights[0]
    q = 1 / len(weights)

    if target_q1 <= 0 or target_q1 >= 1:
        return 2.0

    skew = math.log(q) / math.log(target_q1)
    return max(1.0, min(skew, 10.0))


T = typing.TypeVar("T", covariant=True)


# =============================================================================
# SkewIndex
# =============================================================================

class SkewIndex(BaseIndex[T], typing.Generic[T]):
    """
    Index with power-law distribution.
    A single skew parameter instead of a list of weights.

    skew = 1.0 — uniform distribution
    skew = 2.0 — moderate skew towards the beginning (earlier values are more frequent)
    skew = 3.0+ — strong skew
    """
    _skew: float

    def __init__(self, skew: float, specification: ISpecification[T]):
        self._skew = skew
        super().__init__(specification)

    def _select_idx(self) -> int:
        """Selects an index with power-law distribution. O(1)"""
        n = len(self._values)
        # Power-law distribution: idx = n * (1 - random)^skew
        # At skew=1: uniform (25% in each quartile)
        # At skew=2: skew towards the beginning (50% in the first quartile)
        # At skew=3: strong skew (63% in the first quartile)
        idx = int(n * (1 - random.random()) ** self._skew)
        return min(idx, n - 1)


# =============================================================================
# SkewDistributor
# =============================================================================

class SkewDistributor(BaseDistributor[T], typing.Generic[T]):
    """
    Distributor with power-law distribution.

    A single skew parameter instead of a list of weights:
    - skew = 1.0 — uniform distribution
    - skew = 2.0 — moderate skew (first 20% receive ~60% of calls)
    - skew = 3.0 — strong skew (first 10% receive ~70% of calls)

    Advantages:
    - O(1) value selection (vs O(n) for Distributor)
    - A single parameter instead of a list of weights
    - No problem of value migration between indexes
    """
    _skew: float

    def __init__(
            self,
            delegate: IM2ODistributor[T],
            skew: float = 2.0,
            mean: float | None = None,
    ):
        self._skew = skew
        super().__init__(delegate=delegate, mean=mean)

    def _create_index(self, specification: ISpecification[T]) -> SkewIndex[T]:
        return SkewIndex(self._skew, specification)
