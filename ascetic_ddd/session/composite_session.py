import typing
from contextlib import asynccontextmanager, AsyncExitStack

from ascetic_ddd.session.events import SessionScopeStartedEvent, SessionScopeEndedEvent
from ascetic_ddd.session.interfaces import ISessionPool, ISession
from ascetic_ddd.signals.composite_signal import AsyncCompositeSignal
from ascetic_ddd.signals.interfaces import IAsyncSignal


__all__ = (
    "CompositeSessionPool",
    "CompositeSession",
)


class CompositeSessionPool:
    _delegates: typing.Iterable[ISessionPool]

    def __init__(self, *delegates: ISessionPool) -> None:
        self._delegates = delegates

    @property
    def on_session_started(self) -> IAsyncSignal[SessionScopeStartedEvent]:
        return AsyncCompositeSignal(*(i.on_session_started for i in self._delegates))

    @property
    def on_session_ended(self) -> IAsyncSignal[SessionScopeEndedEvent]:
        return AsyncCompositeSignal(*(i.on_session_ended for i in self._delegates))

    @asynccontextmanager
    async def session(self):
        async with AsyncExitStack() as stack:
            delegates = [
                await stack.enter_async_context(pool.session())
                for pool in self._delegates
            ]
            yield CompositeSession(delegates)

    def __getitem__(self, item):
        return list(self._delegates)[item]


class CompositeSession:
    _delegates: typing.Iterable[ISession]
    _parent: typing.Optional["CompositeSession"]

    def __init__(self, delegates: typing.Iterable[ISession],  parent: typing.Optional["CompositeSession"] = None):
        self._delegates = delegates
        self._parent = parent

    @property
    def on_atomic_started(self) -> IAsyncSignal[SessionScopeStartedEvent]:
        return AsyncCompositeSignal(*(i.on_atomic_started for i in self._delegates))

    @property
    def on_atomic_ended(self) -> IAsyncSignal[SessionScopeEndedEvent]:
        return AsyncCompositeSignal(*(i.on_atomic_ended for i in self._delegates))

    @asynccontextmanager
    async def atomic(self):
        async with AsyncExitStack() as stack:
            delegates = [
                await stack.enter_async_context(d.atomic())
                for d in self._delegates
            ]
            yield CompositeAtomicSession(delegates, self)

    def __getattr__(self, item):
        for delegate in self._delegates:
            if hasattr(delegate, item):
                return getattr(delegate, item)
        raise AttributeError

    def __getitem__(self, item):
        return list(self._delegates)[item]


class CompositeAtomicSession(CompositeSession):
    pass
