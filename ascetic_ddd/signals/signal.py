import copy
import typing
import collections

from collections.abc import Callable, Hashable

from ascetic_ddd.disposable import IDisposable
from ascetic_ddd.disposable.disposable import Disposable
from ascetic_ddd.signals.interfaces import ISyncSignal, IAsyncSignal

EventT = typing.TypeVar("EventT")


class SyncSignal(ISyncSignal[EventT], typing.Generic[EventT]):

    def __init__(self):
        self._observers: collections.OrderedDict[Hashable, Callable[[EventT], None]] = collections.OrderedDict()

    def attach(self, observer: Callable[[EventT], None], observer_id: Hashable | None = None) -> IDisposable:
        observer_id = observer_id or self._make_id(observer)
        if observer_id not in self._observers:
            self._observers[observer_id] = observer

        async def detach():
            self.detach(observer, observer_id)

        return Disposable(detach)

    def detach(self, observer: Callable[[EventT], None], observer_id: Hashable | None = None):
        observer_id = observer_id or self._make_id(observer)
        del self._observers[observer_id]

    def notify(self, event: EventT):
        for observer in self._observers.values():
            observer(event)

    @staticmethod
    def _make_id(target) -> Hashable:
        if hasattr(target, "__func__"):
            return (id(target.__self__), id(target.__func__))
        return id(target)

    def __copy__(self):
        c = copy.copy(super())
        c._observers = collections.OrderedDict()
        return c


class AsyncSignal(IAsyncSignal[EventT], typing.Generic[EventT]):

    def __init__(self):
        self._observers: collections.OrderedDict[Hashable, Callable[[EventT], typing.Awaitable[None]]] = collections.OrderedDict()

    def attach(self, observer: Callable[[EventT], typing.Awaitable[None]], observer_id: Hashable | None = None) -> IDisposable:
        observer_id = observer_id or self._make_id(observer)
        if observer_id not in self._observers:
            self._observers[observer_id] = observer

        async def detach():
            self.detach(observer, observer_id)

        return Disposable(detach)

    def detach(self, observer: Callable[[EventT], typing.Awaitable[None]], observer_id: Hashable | None = None):
        observer_id = observer_id or self._make_id(observer)
        del self._observers[observer_id]

    async def notify(self, event: EventT):
        for observer in self._observers.values():
            await observer(event)

    @staticmethod
    def _make_id(target) -> Hashable:
        if hasattr(target, "__func__"):
            return (id(target.__self__), id(target.__func__))
        return id(target)

    def __copy__(self):
        c = copy.copy(super())
        c._observers = collections.OrderedDict()
        return c
