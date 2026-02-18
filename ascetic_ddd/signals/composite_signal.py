import copy
import typing

from collections.abc import Callable, Hashable

from ascetic_ddd.disposable import IDisposable
from ascetic_ddd.disposable.disposable import Disposable
from ascetic_ddd.signals.interfaces import ISyncSignal, IAsyncSignal

__all__ = ('SyncCompositeSignal', 'AsyncCompositeSignal',)


EventT = typing.TypeVar("EventT")


class SyncCompositeSignal(ISyncSignal[EventT], typing.Generic[EventT]):
    _delegates: typing.Iterable[ISyncSignal[EventT]]

    def __init__(self, *delegates: ISyncSignal[EventT]):
        self._delegates = delegates

    def attach(self, observer: Callable[[EventT], None], observer_id: Hashable | None = None) -> IDisposable:
        disposables = []
        for delegate in self._delegates:
            disposables.append(delegate.attach(observer, observer_id))

        async def detach():
            for disposable in disposables:
                await disposable.dispose()

        return Disposable(detach)

    def detach(self, observer: Callable[[EventT], None], observer_id: Hashable | None = None):
        for delegate in self._delegates:
            delegate.detach(observer, observer_id)

    def notify(self, event: EventT):
        for delegate in self._delegates:
            delegate.notify(event)

    def __copy__(self):
        c = copy.copy(super())
        c._delegates = tuple(copy.copy(i) for i in self._delegates)
        return c


class AsyncCompositeSignal(IAsyncSignal[EventT], typing.Generic[EventT]):
    _delegates: typing.Iterable[IAsyncSignal[EventT]]

    def __init__(self, *delegates: IAsyncSignal[EventT]):
        self._delegates = delegates

    def attach(self, observer: Callable[[EventT], typing.Awaitable[None]], observer_id: Hashable | None = None) -> IDisposable:
        disposables = []
        for delegate in self._delegates:
            disposables.append(delegate.attach(observer, observer_id))

        async def detach():
            for disposable in disposables:
                await disposable.dispose()

        return Disposable(detach)

    def detach(self, observer: Callable[[EventT], typing.Awaitable[None]], observer_id: Hashable | None = None):
        for delegate in self._delegates:
            delegate.detach(observer, observer_id)

    async def notify(self, event: EventT):
        for delegate in self._delegates:
            await delegate.notify(event)

    def __copy__(self):
        c = copy.copy(super())
        c._delegates = tuple(copy.copy(i) for i in self._delegates)
        return c
