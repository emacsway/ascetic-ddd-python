import typing

from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor, IM2ODistributorFactory
from ascetic_ddd.faker.domain.distributors.m2o.nullable_distributor import NullableDistributor
from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.distributors.o2m.interfaces import IO2MDistributor
from ascetic_ddd.faker.domain.distributors.o2m.weighted_range_distributor import WeightedRangeDistributor
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.signals.signal import AsyncSignal
from ascetic_ddd.faker.domain.distributors.m2o.events import ValueAppendedEvent

__all__ = ('RangeDistributorAdapter', 'RangeDistributorFactory')

T = typing.TypeVar("T")


class RangeDistributorAdapter(IM2ODistributor[T], typing.Generic[T]):
    """
    Adapter of O2M range distributor to the IM2ODistributor interface.

    Uses an O2M distributor to generate a number from a range,
    then looks up the value by that number in a dictionary.

    If the value is not found -- raises Cursor(),
    signaling the calling code to create a new value for this slot.

    Example:
        from ascetic_ddd.faker.domain.distributors.o2m import (
            WeightedRangeDistributor,
            RangeDistributorAdapter,
        )

        range_dist = WeightedRangeDistributor.exponential_decay(0, 99, decay=0.7)
        adapter = RangeDistributorAdapter(range_dist)

        # In provider:
        try:
            company = await adapter.next(session)
        except Cursor as cursor:
            company = await create_company(cursor.position)
            await cursor.append(session, company)
    """
    _distributor: IO2MDistributor
    _values: dict[int, T]
    _provider_name: str | None
    _on_appended: IAsyncSignal[ValueAppendedEvent[T]]

    def __init__(self, distributor: IO2MDistributor):
        """
        Args:
            distributor: O2M distributor that returns numbers from a range
        """
        self._distributor = distributor
        self._values = {}
        self._provider_name = None
        self._on_appended = AsyncSignal[ValueAppendedEvent[T]]()

    @property
    def on_appended(self) -> IAsyncSignal[ValueAppendedEvent[T]]:
        return self._on_appended

    async def next(
            self,
            session: ISession,
            specification: ISpecification[T] | None = None,
    ) -> T:
        """
        Returns a value from the dictionary by a random number.

        Raises:
            Cursor(): if there is no value in the dictionary for the slot.
            cursor.position -- the slot number.
            cursor.append(session, value) -- add a value.
        """
        num = self._distributor.distribute()

        if num not in self._values:
            raise Cursor(
                position=num,
                callback=self._append,
            )

        value = self._values[num]

        # Check specification if provided
        if specification is not None and not await specification.is_satisfied_by(session, value):
            # Value does not satisfy the specification -- try again
            return await self.next(session, specification)

        return value

    async def _append(self, session: ISession, value: T, position: int | None = None):
        """
        Adds a value to the dictionary.

        Args:
            session: Session
            value: Value to add
            position: Slot number (key in the dictionary).
        """
        self._values[position] = value  # type: ignore[index]
        await self._on_appended.notify(ValueAppendedEvent(session, value, position))

    async def append(self, session: ISession, value: T):
        await self._append(session, value, None)

    @property
    def provider_name(self) -> str | None:
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value: str):
        if self._provider_name is None:
            self._provider_name = value

    async def setup(self, session: ISession):
        pass

    async def cleanup(self, session: ISession):
        self._values.clear()

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self

    def __len__(self) -> int:
        """Number of values in the dictionary."""
        return len(self._values)

    def __contains__(self, value: T) -> bool:
        """Checks whether the value is present in the dictionary."""
        return value in self._values.values()


class RangeDistributorFactory(IM2ODistributorFactory[T], typing.Generic[T]):
    """
    Factory of M2O distributors based on a range.

    Creates a RangeDistributorAdapter with a WeightedRangeDistributor inside.

    Example:
        factory = RangeDistributorFactory(min_val=0, max_val=99)

        # Create a distributor with weights
        dist = factory(weights=[0.7, 0.2, 0.1])

        # Create a distributor with skew (exponential decay)
        dist = factory(skew=2.0)

        # Usage
        try:
            value = await dist.next(session)
        except ICursor as cursor:
            new_value = create_value(cursor.position)
            await cursor.append(session, new_value)
    """
    _min_val: int
    _max_val: int

    def __init__(self, min_val: int, max_val: int):
        """
        Args:
            min_val: Minimum value of the range (inclusive)
            max_val: Maximum value of the range (inclusive)
        """
        self._min_val = min_val
        self._max_val = max_val

    def __call__(
        self,
        weights: list[float] | None = None,
        skew: float | None = None,
        mean: float | None = None,
        null_weight: float = 0,
        sequence: bool = False,
    ) -> IM2ODistributor[T]:
        """
        Creates an M2O distributor.

        Args:
            weights: Weights for each value in the range
            skew: Skew parameter for exponential decay (decay = 1/skew)
            mean: Not used (for interface compatibility)
            null_weight: Probability of returning None (0-1)
            sequence: Not used (for interface compatibility)

        Returns:
            RangeDistributorAdapter with the corresponding WeightedRangeDistributor
        """
        if weights is not None:
            range_dist = WeightedRangeDistributor(
                self._min_val,
                self._max_val,
                weights=weights,
            )
        elif skew is not None and skew > 1:
            # skew -> decay: the larger the skew, the smaller the decay
            decay = 1.0 / skew
            range_dist = WeightedRangeDistributor.exponential_decay(
                self._min_val,
                self._max_val,
                decay=decay,
            )
        else:
            # Uniform distribution
            range_dist = WeightedRangeDistributor.uniform(
                self._min_val,
                self._max_val,
            )

        adapter = RangeDistributorAdapter(range_dist)

        if null_weight > 0:
            return NullableDistributor(adapter, null_weight=null_weight)

        return adapter
