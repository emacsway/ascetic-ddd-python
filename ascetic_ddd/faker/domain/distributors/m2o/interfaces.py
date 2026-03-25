import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.option import Option
from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.faker.domain.distributors.m2o.events import ValueAppendedEvent
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification

__all__ = (
    'IM2ODistributor',
    'IM2ODistributorFactory',
    'ICursor',
)


T = typing.TypeVar("T")


class IM2ODistributor(typing.Generic[T], metaclass=ABCMeta):

    @property
    @abstractmethod
    def on_appended(self) -> IAsyncSignal[ValueAppendedEvent[T]]:
        raise NotImplementedError

    @abstractmethod
    async def next(
            self,
            session: ISession,  # To get Redis connect from it.
            specification: ISpecification[T],
    ) -> Option[T]:
        """
        Returns next value from distribution.
        Raises ICursor(num) when mean is reached, signaling caller to create new value.
        num is sequence position (for SequenceDistributor) or -1 (not set).
        """
        raise NotImplementedError

    @abstractmethod
    async def append(self, session: ISession, value: T):
        """
        Appends value to the distributor.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def provider_name(self):
        raise NotImplementedError

    @provider_name.setter
    @abstractmethod
    def provider_name(self, value):
        raise NotImplementedError

    @abstractmethod
    async def setup(self, session: ISession):
        raise NotImplementedError

    @abstractmethod
    async def cleanup(self, session: ISession):
        raise NotImplementedError

    @abstractmethod
    def __copy__(self):
        raise NotImplementedError

    @abstractmethod
    def __deepcopy__(self, memodict={}):
        raise NotImplementedError


class ICursor(typing.Generic[T], StopAsyncIteration, metaclass=ABCMeta):
    @property
    @abstractmethod
    def position(self):
        raise NotImplementedError

    @abstractmethod
    async def append(self, session: ISession, value: T):
        raise NotImplementedError


class IM2ODistributorFactory(typing.Protocol[T]):

    def __call__(
        self,
        weights: list[float] | None = None,
        skew: float | None = None,
        mean: float | None = None,
        null_weight: float = 0,
        name: str | None = None,
        store: IM2ODistributor[T] | None = None,
    ) -> IM2ODistributor[T]:
        """
        Factory for Distributor.

        Args:
            weights: If a weights sequence is specified, selections are made according to the relative weights.
            skew: Skew parameter (1.0 = uniform, 2.0+ = skewed towards the beginning). Default = 2.0
            mean: Average number of uses for each value.
            null_weight: Probability of returning None (0-1)
            name: Provider name for distributor (used for PG table naming).
        """
        ...
