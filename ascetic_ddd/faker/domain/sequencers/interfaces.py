import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.session.interfaces import ISession

__all__ = (
    'ISequencer',
    'IStringable',
)


T = typing.TypeVar("T")


class IStringable(typing.Protocol):
    def __str__(self) -> str:
        ...


class ISequencer(metaclass=ABCMeta):

    @abstractmethod
    async def next(
            self,
            session: ISession,
            scope: IStringable | None = None,
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
