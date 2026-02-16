import collections
import typing

from ascetic_ddd.disposable import Disposable, IDisposable
from ascetic_ddd.event_bus.interfaces import IEventBus, IEventHandler

__all__ = ("InMemoryEventBus",)

SessionT_co = typing.TypeVar("SessionT_co", covariant=True)
UriT_co = typing.TypeVar("UriT_co", covariant=True)
EventT_co = typing.TypeVar("EventT_co", covariant=True)


class InMemoryEventBus(IEventBus[SessionT_co, UriT_co, EventT_co], typing.Generic[SessionT_co, UriT_co, EventT_co]):
    def __init__(self) -> None:
        self._subscribers = collections.defaultdict(list)

    async def publish(self, session: SessionT_co, uri: UriT_co, event: EventT_co) -> None:
        for handler in self._subscribers[uri]:
            await handler(session, uri, event)

    async def subscribe(self, uri: UriT_co, handler: IEventHandler[SessionT_co, UriT_co, EventT_co]) -> IDisposable:
        self._subscribers[uri].append(handler)

        async def callback() -> None:
            await self.unsubscribe(uri, handler)

        return Disposable(callback)

    async def unsubscribe(self, uri: UriT_co, handler: IEventHandler[SessionT_co, UriT_co, EventT_co]) -> None:
        self._subscribers[uri].remove(handler)
