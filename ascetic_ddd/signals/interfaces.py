import typing
from collections.abc import Callable, Hashable
from abc import ABCMeta, abstractmethod

from ascetic_ddd.disposable.interfaces import IDisposable

EventT = typing.TypeVar("EventT")


class ISyncSignal(typing.Generic[EventT], metaclass=ABCMeta):

    @abstractmethod
    def attach(self, observer: Callable[[EventT], None], observer_id: Hashable | None = None) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    def detach(self, observer: Callable[[EventT], None], observer_id: Hashable | None = None):
        raise NotImplementedError

    @abstractmethod
    def notify(self, event: EventT):
        raise NotImplementedError


class IAsyncSignal(typing.Generic[EventT], metaclass=ABCMeta):

    @abstractmethod
    def attach(self, observer: Callable[[EventT], typing.Awaitable[None]], observer_id: Hashable | None = None) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    def detach(self, observer: Callable[[EventT], typing.Awaitable[None]], observer_id: Hashable | None = None):
        raise NotImplementedError

    @abstractmethod
    async def notify(self, event: EventT):
        raise NotImplementedError
