import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification

__all__ = (
    'ISequencer',
)


T = typing.TypeVar("T")


class ISequencer(metaclass=ABCMeta):

    @abstractmethod
    async def next(
            self,
            session: ISession,
            specification: ISpecification[T],
    ) -> int:
        """
        Returns next value from sequencer.
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


class ISequencerFactory(typing.Protocol):

    def __call__(
        self,
        name: str | None = None,
    ) -> ISequencer:
        """
        Factory for Sequencer.

        Args:
            name: Provider name for distributor (used for PG table naming).
        """
        ...
