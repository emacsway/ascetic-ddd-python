import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.disposable import IDisposable

__all__ = (
    "IEventBus",
    "IEventHandler",
)

SessionT = typing.TypeVar("SessionT")
EventT = typing.TypeVar("EventT")

SessionT_contra = typing.TypeVar("SessionT_contra", contravariant=True)
EventT_contra = typing.TypeVar("EventT_contra", contravariant=True)


class IEventHandler(typing.Protocol[SessionT_contra, EventT_contra]):
    def __call__(self, session: SessionT_contra, uri: str, event: EventT_contra):
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
