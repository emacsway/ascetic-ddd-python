import math
import random
import typing
from abc import abstractmethod, ABCMeta

from ascetic_ddd.faker.domain.distributors.m2o import WriteDistributor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.option import Option
from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.faker.domain.distributors.m2o.events import ValueAppendedEvent
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification

__all__ = ('BaseDistributor', 'WeightedDistributor',)

T = typing.TypeVar("T")


class BaseDistributor(IM2ODistributor[T], typing.Generic[T], metaclass=ABCMeta):
    """
    Base class for in-memory distributors.
    """
    _mean: float = 50
    _default_spec: ISpecification[T]
    _provider_name: str | None = None
    _store: WriteDistributor[T]

    def __init__(self, store: WriteDistributor[T], mean: float | None = None):
        self._store = store
        if mean is not None:
            self._mean = mean
        super().__init__()

    async def next(self, session: ISession, specification: ISpecification[T]) -> Option[T]:
        return await self._store.next_with_strategy(session, specification, self._distribute)

    @abstractmethod
    def _distribute(self, n: int) -> int:
        raise NotImplementedError

    async def append(self, session: ISession, value: T):
        await self._store.append(session, value)

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        if self._provider_name is None:
            self._provider_name = value

    @property
    def on_appended(self) -> IAsyncSignal[ValueAppendedEvent[T]]:
        return self._store.on_appended

    async def setup(self, session: ISession):
        pass

    async def cleanup(self, session: ISession):
        pass

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self


class WeightedDistributor(BaseDistributor[T], typing.Generic[T]):
    _weights: list[float]

    def __init__(
            self,
            store: WriteDistributor[T],
            weights: typing.Iterable[float] = tuple(),
            mean: float | None = None,
    ):
        self._weights = list(weights)
        super().__init__(store=store, mean=mean)

    def _distribute(self, n: int) -> int:
        """Selects a value index considering weights and skew."""

        # Select a partition by weights — O(w)
        partition_idx = random.choices(
            range(len(self._weights)),
            weights=self._weights,
            k=1
        )[0]

        # Calculate partition boundaries — O(1)
        partition_size = n / len(self._weights)
        start = int(partition_idx * partition_size)
        end = int((partition_idx + 1) * partition_size)
        if end <= start:
            end = start + 1
        end = min(end, n)

        # Calculate local skew from the weight ratio of adjacent partitions — O(1)
        # Use the LEFT partition and shift towards the END — this compensates for the fact
        # that earlier values receive more calls (available longer during dynamic creation).
        # For weights=[0.7, 0.2, 0.07, 0.03]:
        #   partition 0: first → local_skew=1.0 (uniform)
        #   partition 1: ratio=3.5 → local_skew≈2.81 (shift towards end, closer to partition 0)
        #   partition 2: ratio=2.86 → local_skew≈2.52
        #   partition 3: ratio=2.33 → local_skew≈2.22
        if partition_idx > 0:
            prev_weight = self._weights[partition_idx - 1]
            curr_weight = self._weights[partition_idx]
            if curr_weight > 0:
                ratio = prev_weight / curr_weight
                # ratio > 1 → shift towards end of partition (closer to previous)
                # ratio = 1 → uniform distribution
                local_skew = max(1.0, math.log2(ratio) + 1)
                # local_skew = max(1.0, math.log2(ratio) * 0.5 + 1)  # smoother skew
            else:
                local_skew = 2.0
        else:
            # First partition — uniform distribution
            local_skew = 1.0

        # Select a value considering skew — O(1)
        # Shift towards the END of partition: end - 1 - local_idx
        size = end - start
        local_idx = int(size * (1 - random.random()) ** local_skew)
        local_idx = min(local_idx, size - 1)
        return end - 1 - local_idx
