import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.disposable import IDisposable

__all__ = (
    "IEventBus",
    "IEventHandler",
)

T_Session = typing.TypeVar("T_Session", covariant=True)
T_Uri = typing.TypeVar("T_Uri", covariant=True)
T_Event = typing.TypeVar("T_Event", covariant=True)


class IEventHandler(typing.Protocol[T_Session, T_Uri, T_Event]):
    def __call__(self, session: T_Session, uri: T_Uri, event: T_Event):
        ...


class IEventBus(typing.Protocol[T_Session, T_Uri, T_Event], metaclass=ABCMeta):
    @abstractmethod
    async def publish(self, session: T_Session, uri: T_Uri, event: T_Event) -> None:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(self, uri: T_Uri, handler: IEventHandler[T_Session, T_Uri, T_Event]) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe(self, uri: T_Uri, handler: IEventHandler[T_Session, T_Uri, T_Event]) -> None:
        raise NotImplementedError
