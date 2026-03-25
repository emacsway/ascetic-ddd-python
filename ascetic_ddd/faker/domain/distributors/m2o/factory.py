import typing

from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.faker.domain.distributors.m2o.weighted_distributor import WeightedDistributor
from ascetic_ddd.faker.domain.distributors.m2o.nullable_distributor import NullableDistributor
from ascetic_ddd.faker.domain.distributors.m2o.skew_distributor import SkewDistributor
from ascetic_ddd.faker.domain.distributors.m2o.write_distributor import WriteDistributor

__all__ = ('distributor_factory',)


T = typing.TypeVar("T")


def distributor_factory(
    weights: list[float] | None = None,
    skew: float | None = None,
    mean: float | None = None,
    null_weight: float = 0,
    name: str | None = None,
    store: WriteDistributor[T] | None = None,
) -> IM2ODistributor[T]:
    """
    Factory for Distributor.

    Args:
        weights: If a weights sequence is specified, selections are made according to the relative weights.
        skew: Skew parameter (1.0 = uniform, 2.0+ = skew towards the beginning). Default = 2.0
        mean: Average number of usages for each value.
        null_weight: Probability of returning None (0-1)
        name: Provider name for distributor (used for PG table naming).
        store: Shared WriteDistributor for CQRS. When provided, multiple
            distributors share the same value pool.
    """
    if store is None:
        store = WriteDistributor[T]()
    if weights is not None:
        dist: IM2ODistributor[T] = WeightedDistributor[T](store=store, weights=weights, mean=mean)
    elif skew is not None:
        dist = SkewDistributor[T](store=store, skew=skew, mean=mean)
    else:
        dist = store
    if null_weight:
        dist = NullableDistributor[T](delegate=dist, null_weight=null_weight)
    if name is not None:
        dist.provider_name = name
    return dist
