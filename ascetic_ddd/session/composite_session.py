import typing
from collections.abc import Hashable
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

    def _split_aspect(self, aspect: typing.Hashable) -> tuple[str | None, typing.Hashable]:
        if isinstance(aspect, str) and "." in aspect:
            item, inner_aspect = aspect.split('.', maxsplit=1)
            return item, inner_aspect
        return None, aspect

    def attach(self, aspect, observer, id_: Hashable | None = None):
        item, inner_aspect = self._split_aspect(aspect)
        if item is not None:
            return self[item].attach(inner_aspect, observer, id_)

    def detach(self, aspect, observer, id_: Hashable | None = None):
        item, inner_aspect = self._split_aspect(aspect)
        if item is not None:
            return self[item].detach(inner_aspect, observer, id_)

    def notify(self, aspect, *args, **kwargs):
        item, inner_aspect = self._split_aspect(aspect)
        if item is not None:
            return self[item].notify(inner_aspect, *args, **kwargs)

    async def anotify(self, aspect, *args, **kwargs):
        item, inner_aspect = self._split_aspect(aspect)
        if item is not None:
            return await self[item].anotify(inner_aspect, *args, **kwargs)


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

    def _split_aspect(self, aspect: typing.Hashable) -> tuple[str | None, typing.Hashable]:
        if isinstance(aspect, str) and "." in aspect:
            item, inner_aspect = aspect.split('.', maxsplit=1)
            return item, inner_aspect
        return None, aspect

    def attach(self, aspect, observer, id_: Hashable | None = None):
        item, inner_aspect = self._split_aspect(aspect)
        if item is not None:
            return self[item].attach(inner_aspect, observer, id_)

    def detach(self, aspect, observer, id_: Hashable | None = None):
        item, inner_aspect = self._split_aspect(aspect)
        if item is not None:
            return self[item].detach(inner_aspect, observer, id_)

    def notify(self, aspect, *args, **kwargs):
        item, inner_aspect = self._split_aspect(aspect)
        if item is not None:
            return self[item].notify(inner_aspect, *args, **kwargs)

    async def anotify(self, aspect, *args, **kwargs):
        item, inner_aspect = self._split_aspect(aspect)
        if item is not None:
            return await self[item].anotify(inner_aspect, *args, **kwargs)


class CompositeTransactionSession(CompositeSession):
    pass
