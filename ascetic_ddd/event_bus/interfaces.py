import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.disposable import IDisposable

__all__ = (
    "IEventBus",
    "IEventHandler",
)

SessionT = typing.TypeVar("SessionT")
EventT = typing.TypeVar("EventT")


class IEventHandler(typing.Protocol[SessionT, EventT]):
    def __call__(self, session: SessionT, uri: str, event: EventT):
        ...


class IEventBus(typing.Generic[SessionT], metaclass=ABCMeta):
    @abstractmethod
    async def publish(self, session: SessionT, uri: str, event: EventT) -> None:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(self, uri: str, handler: IEventHandler[SessionT, EventT]) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe(self, uri: str, handler: IEventHandler[SessionT, EventT]) -> None:
        raise NotImplementedError
