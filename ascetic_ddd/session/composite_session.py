import typing
from contextlib import asynccontextmanager, AsyncExitStack

from ascetic_ddd.session.interfaces import ISessionPool, ISession

__all__ = (
    "CompositeSessionPool",
    "CompositeSession",
)


class CompositeSessionPool(ISessionPool):
    _delegates: typing.Iterable[ISessionPool]

    def __init__(self, *delegates: ISessionPool) -> None:
        self._delegates = delegates

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


class CompositeSession(ISession):
    _delegates: typing.Iterable[ISession]
    _parent: typing.Optional["CompositeSession"]

    def __init__(self, delegates: typing.Iterable[ISession],  parent: typing.Optional["CompositeSession"] = None):
        self._delegates = delegates
        self._parent = parent

    @asynccontextmanager
    async def atomic(self):
        async with AsyncExitStack() as stack:
            delegates = [
                await stack.enter_async_context(d.atomic())
                for d in self._delegates
            ]
            yield CompositeTransactionSession(delegates, self)

    def __getattr__(self, item):
        for delegate in self._delegates:
            if hasattr(delegate, item):
                return getattr(delegate, item)
        raise AttributeError

    def __getitem__(self, item):
        return list(self._delegates)[item]


class CompositeTransactionSession(CompositeSession):
    pass
