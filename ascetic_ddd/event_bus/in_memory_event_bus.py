import collections
import typing

from ascetic_ddd.disposable import Disposable, IDisposable
from ascetic_ddd.event_bus.interfaces import IEventBus, IEventHandler

__all__ = ("InMemoryEventBus",)

T_Session = typing.TypeVar("T_Session", covariant=True)
T_Uri = typing.TypeVar("T_Uri", covariant=True)
T_Event = typing.TypeVar("T_Event", covariant=True)


class InMemoryEventBus(IEventBus[T_Session, T_Uri, T_Event], typing.Generic[T_Session, T_Uri, T_Event]):
    def __init__(self) -> None:
        self._subscribers = collections.defaultdict(list)

    async def publish(self, session: T_Session, uri: T_Uri, event: T_Event) -> None:
        for handler in self._subscribers[uri]:
            await handler(session, uri, event)

    async def subscribe(self, uri: T_Uri, handler: IEventHandler[T_Session, T_Uri, T_Event]) -> IDisposable:
        self._subscribers[uri].append(handler)

        async def callback() -> None:
            await self.unsubscribe(uri, handler)

        return Disposable(callback)

    async def unsubscribe(self, uri: T_Uri, handler: IEventHandler[T_Session, T_Uri, T_Event]) -> None:
        self._subscribers[uri].remove(handler)
