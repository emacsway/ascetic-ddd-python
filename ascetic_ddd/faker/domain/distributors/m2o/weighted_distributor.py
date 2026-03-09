import math
import random
import typing
from abc import abstractmethod

from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor, IExternalSource
from ascetic_ddd.option import Option, Some
from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.faker.domain.distributors.m2o.events import ValueAppendedEvent
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification

__all__ = ('BaseIndex', 'BaseDistributor', 'Index', 'WeightedDistributor',)

T = typing.TypeVar("T")


# =============================================================================
# BaseIndex
# =============================================================================

class BaseIndex(typing.Generic[T]):
    """
    Base class for distributor indexes.
    """
    _specification: ISpecification[T]
    _read_offset: int
    _values: list[T]
    _value_set: set[T]

    def __init__(self, specification: ISpecification[T]):
        self._specification = specification
        self._read_offset = 0
        self._values = []
        self._value_set = set()

    @property
    def read_offset(self):
        return self._read_offset

    @read_offset.setter
    def read_offset(self, val: int):
        self._read_offset = val

    def __contains__(self, value: T):
        return value in self._value_set

    def __len__(self):
        return len(self._values)

    def values(self, offset: int = 0):
        if offset == 0:
            return self._values
        else:
            return self._values[offset:]

    def append(self, value: T, read_offset: int = 0):
        if value not in self._value_set:
            self._values.append(value)
            self._value_set.add(value)
        if read_offset:
            self._read_offset = read_offset

    def remove(self, value: T) -> bool:
        """Removes an object from the index. Returns True if the object was removed."""
        if value not in self._value_set:
            return False
        self._value_set.discard(value)
        self._values.remove(value)
        return True

    def get_relative_position(self, value: T) -> float | None:
        """Returns the relative position of an object (0.0 - 1.0) or None if not found."""
        if value not in self._value_set:
            return None
        idx = self._values.index(value)
        n = len(self._values)
        return idx / n if n > 0 else 0.0

    def insert_at_relative_position(self, value: T, relative_position: float) -> None:
        """Inserts an object at the position corresponding to the relative position."""
        if value in self._value_set:
            return
        n = len(self._values)
        idx = int(relative_position * n)
        idx = max(0, min(idx, n))
        self._values.insert(idx, value)
        self._value_set.add(value)

    async def populate_from(self, session: ISession, source: 'BaseIndex') -> None:
        values_length = len(source)
        if self._read_offset < values_length:
            current_offset = self._read_offset
            self._read_offset = values_length
            for value in source.values(current_offset):
                if await self._specification.is_satisfied_by(session, value):
                    self.append(value, values_length)

    @abstractmethod
    def _select_idx(self) -> int:
        """Selects a value index. Implementation depends on the distribution strategy."""
        raise NotImplementedError

    def next(self, expected_mean: float) -> T:
        """
        Returns a random value from the index.
        Raises StopIteration with probability 1/expected_mean (signal to create a new one).
        """
        n = len(self._values)
        if n == 0:
            raise StopIteration

        # Probabilistically signal the need to create a new value
        if random.random() < 1.0 / expected_mean:
            raise StopIteration

        return self._values[self._select_idx()]

    def select(self) -> T:
        """Select a value without probabilistic rejection (fallback)."""
        n = len(self._values)
        if n == 0:
            raise StopIteration

        return self._values[self._select_idx()]

    def first(self) -> T:
        return self._values[0]


# =============================================================================
# BaseDistributor
# =============================================================================

class BaseDistributor(IM2ODistributor[T], typing.Generic[T]):
    """
    Base class for in-memory distributors.
    """
    _mean: float = 50
    _indexes: dict[ISpecification, BaseIndex[T]]
    _default_spec: ISpecification
    _provider_name: str | None = None
    _external_source: IExternalSource[T] | None = None
    _delegate: IM2ODistributor[T]

    def __init__(self, delegate: IM2ODistributor[T], mean: float | None = None):
        self._delegate = delegate
        if mean is not None:
            self._mean = mean
        self._default_spec = EmptySpecification()
        self._indexes = dict()
        self._indexes[self._default_spec] = self._create_index(self._default_spec)
        self._external_source = None
        super().__init__()

    def bind_external_source(self, external_source: typing.Any) -> None:
        """Binds an external data source (repository)."""
        if not isinstance(external_source, IExternalSource):
            raise TypeError("Expected IExternalSource, got %s" % type(external_source))
        self._external_source = external_source
        self._external_source = None  # Temporary disable

    @abstractmethod
    def _create_index(self, specification: ISpecification[T]) -> BaseIndex[T]:
        """Creates an index for a specification. Implementation depends on the distributor type."""
        raise NotImplementedError

    async def next(
            self,
            session: ISession,
            specification: ISpecification[T],
    ) -> Option[T]:
        if specification != self._default_spec:
            if specification not in self._indexes:
                self._indexes[specification] = self._create_index(specification)
            target_index = self._indexes[specification]
            source_index = self._indexes[self._default_spec]
            await target_index.populate_from(session, source_index)

        target_index = self._indexes[specification]

        try:
            value = target_index.next(self._mean)
        except StopIteration:
            try:
                return await self._delegate.next(session, specification)
            except Cursor as cursor:
                raise Cursor(
                    position=-1,
                    callback=self._append,
                    delegate=cursor
                )

        # Check if the object has become stale (e.g. it was modified)
        if not await specification.is_satisfied_by(session, value):
            await self._relocate_stale_value(session, value, specification)
            # Retry
            return await self.next(session, specification)

        return Some(value)

    async def _relocate_stale_value(self, session: ISession, value: T, current_spec: ISpecification[T]) -> None:
        """
        Relocates a stale object from the current index to suitable ones.
        """
        # Remove from the current index
        current_index = self._indexes.get(current_spec)
        if current_index:
            current_index.remove(value)

        # Get the relative position from the default index
        default_index = self._indexes[self._default_spec]
        relative_position = default_index.get_relative_position(value)

        if relative_position is None:
            return

        # Iterate over all indexes (except default and current) and insert where suitable
        for spec, index in self._indexes.items():
            if spec == self._default_spec or spec == current_spec:
                continue
            if await spec.is_satisfied_by(session, value):
                index.insert_at_relative_position(value, relative_position)

    async def _append(self, session: ISession, value: T, position: int):
        if self._external_source:
            return
        if value not in self._indexes[self._default_spec]:
            self._indexes[self._default_spec].append(value)
            # Prevent double notification, self._delegate._append() will be called from Cursor.
            # await self.on_appended.notify(ValueAppendedEvent(session, value, position))

    async def append(self, session: ISession, value: T):
        await self._append(session, value, -1)
        await self._delegate.append(session, value)

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        if self._provider_name is None:
            self._provider_name = value

    @property
    def on_appended(self) -> IAsyncSignal[ValueAppendedEvent[T]]:
        return self._delegate.on_appended

    async def setup(self, session: ISession):
        pass

    async def cleanup(self, session: ISession):
        pass

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self


# =============================================================================
# Index (Weighted)
# =============================================================================

class Index(BaseIndex[T], typing.Generic[T]):
    """
    Index with weighted distribution across partitions.
    """
    _weights: list[float]

    def __init__(self, weights: list[float], specification: ISpecification[T]):
        self._weights = weights
        super().__init__(specification)

    def _select_idx(self) -> int:
        """Selects a value index considering weights and skew."""
        n = len(self._values)

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


# =============================================================================
# WeightedDistributor
# =============================================================================

class WeightedDistributor(BaseDistributor[T], typing.Generic[T]):
    _weights: list[float]

    def __init__(
            self,
            delegate: IM2ODistributor[T],
            weights: typing.Iterable[float] = tuple(),
            mean: float | None = None,
    ):
        self._weights = list(weights)
        super().__init__(delegate=delegate, mean=mean)

    def _create_index(self, specification: ISpecification[T]) -> Index[T]:
        return Index(self._weights, specification)
