import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.disposable import IDisposable

__all__ = (
    "IEventBus",
    "IEventHandler",
)

SessionT_co = typing.TypeVar("SessionT_co", covariant=True)
UriT_co = typing.TypeVar("UriT_co", covariant=True)
EventT_co = typing.TypeVar("EventT_co", covariant=True)


class IEventHandler(typing.Protocol[SessionT_co, UriT_co, EventT_co]):
    def __call__(self, session: SessionT_co, uri: UriT_co, event: EventT_co):
        ...


class IEventBus(typing.Protocol[SessionT_co, UriT_co, EventT_co], metaclass=ABCMeta):
    @abstractmethod
    async def publish(self, session: SessionT_co, uri: UriT_co, event: EventT_co) -> None:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(self, uri: UriT_co, handler: IEventHandler[SessionT_co, UriT_co, EventT_co]) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe(self, uri: UriT_co, handler: IEventHandler[SessionT_co, UriT_co, EventT_co]) -> None:
        raise NotImplementedError
