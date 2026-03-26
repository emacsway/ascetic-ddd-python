import random
import typing
from collections.abc import Callable, Hashable

from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.option import Option, Some
from ascetic_ddd.seedwork.domain.utils.data import hashable
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification

__all__ = ('WriteDistributor', 'Index',)


T = typing.TypeVar("T")


class Index(typing.Generic[T]):
    """
    Index class for distributor.
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
        return self._to_hashable(value) in self._value_set

    def __len__(self):
        return len(self._values)

    def values(self, offset: int = 0):
        if offset == 0:
            return self._values
        else:
            return self._values[offset:]

    def append(self, value: T, read_offset: int = 0):
        hashable_value = self._to_hashable(value)
        if hashable_value not in self._value_set:
            self._values.append(value)
            self._value_set.add(hashable_value)

        if read_offset:
            self._read_offset = read_offset

    def remove(self, value: T) -> bool:
        """Removes an object from the index. Returns True if the object was removed."""
        hashable_value = self._to_hashable(value)
        if hashable_value not in self._value_set:
            return False
        self._value_set.discard(hashable_value)
        self._values.remove(value)
        return True

    def get_relative_position(self, value: T) -> float | None:
        """Returns the relative position of an object (0.0 - 1.0) or None if not found."""
        if self._to_hashable(value) not in self._value_set:
            return None
        idx = self._values.index(value)
        n = len(self._values)
        return idx / n if n > 0 else 0.0

    def insert_at_relative_position(self, value: T, relative_position: float) -> None:
        """Inserts an object at the position corresponding to the relative position."""
        hashable_value = self._to_hashable(value)
        if hashable_value in self._value_set:
            return
        n = len(self._values)
        idx = int(relative_position * n)
        idx = max(0, min(idx, n))
        self._values.insert(idx, value)
        self._value_set.add(hashable_value)

    async def populate_from(self, session: ISession, source: 'Index') -> None:
        values_length = len(source)
        if self._read_offset < values_length:
            current_offset = self._read_offset
            self._read_offset = values_length
            for value in source.values(current_offset):
                if await self._specification.is_satisfied_by(session, value):
                    self.append(value, values_length)

    def next(self, expected_mean: float, distribution_strategy: Callable[[int], int]) -> T:
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

        return self._values[distribution_strategy(n)]

    @staticmethod
    def _to_hashable(value: typing.Any):
        if not isinstance(value, Hashable):
            return hashable(value)
        return value


class WriteDistributor(IM2ODistributor[T], typing.Generic[T]):
    """
    Base class for in-memory distributors.
    """
    _mean: float = 50
    _indexes: dict[ISpecification, Index[T]]
    _default_spec: ISpecification[T]
    _provider_name: str | None = None

    def __init__(self, mean: float | None = None):
        if mean is not None:
            self._mean = mean
        self._default_spec = EmptySpecification[T]()
        self._indexes = dict()
        self._indexes[self._default_spec] = self._create_index(self._default_spec)
        super().__init__()

    def _create_index(self, specification: ISpecification[T]) -> Index[T]:
        return Index(specification)

    async def next(
            self,
            session: ISession,
            specification: ISpecification[T],
    ) -> Option[T]:
        raise Cursor(
            position=-1,
            callback=self._append,
        )

    async def next_with_strategy(
            self,
            session: ISession,
            specification: ISpecification[T],
            distribution_strategy: Callable[[int], int]
    ) -> Option[T]:
        if specification != self._default_spec:
            if specification not in self._indexes:
                self._indexes[specification] = self._create_index(specification)
            target_index = self._indexes[specification]
            source_index = self._indexes[self._default_spec]
            await target_index.populate_from(session, source_index)

        target_index = self._indexes[specification]

        try:
            value = target_index.next(self._mean, distribution_strategy)
        except StopIteration:
            raise Cursor(
                position=-1,
                callback=self._append
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
        if value not in self._indexes[self._default_spec]:
            self._indexes[self._default_spec].append(value)

    async def append(self, session: ISession, value: T):
        await self._append(session, value, -1)

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        if self._provider_name is None:
            self._provider_name = value

    async def setup(self, session: ISession):
        pass

    async def cleanup(self, session: ISession):
        pass

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self
