import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.disposable.interfaces import IDisposable

__all__ = (
    "IMediator",
    "ICommandHandler",
    "IEventHandler",
    "IPipelineHandler",
    "CommandResultT",
)


SessionT_co = typing.TypeVar("SessionT_co", covariant=True)
CommandT_co = typing.TypeVar("CommandT_co", covariant=True)
EventT_co = typing.TypeVar("EventT_co", covariant=True)
CommandResultT = typing.TypeVar("CommandResultT")


class ICommandHandler(typing.Protocol[SessionT_co, CommandT_co]):
    def __call__(self, session: SessionT_co, command: CommandT_co) -> typing.Any:
        ...


class IEventHandler(typing.Protocol[SessionT_co, EventT_co]):
    def __call__(self, session: SessionT_co, event: EventT_co):
        ...


class IPipelineHandler(typing.Protocol[SessionT_co, CommandT_co]):
    @abstractmethod
    async def __call__(
            self, session: SessionT_co, command: CommandT_co, next_: 'ICommandHandler[SessionT_co, CommandT_co]'
    ) -> typing.Any:
        ...


class IMediator(typing.Generic[CommandT_co, EventT_co, SessionT_co], metaclass=ABCMeta):

    @abstractmethod
    async def send(self, session: SessionT_co, command: CommandT_co):
        raise NotImplementedError

    @abstractmethod
    async def register(self, command_type: type[CommandT_co], handler: ICommandHandler[SessionT_co, CommandT_co]) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    async def unregister(self, command_type: type[CommandT_co]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def publish(self, session: SessionT_co, event: EventT_co) -> None:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(
            self, event_type: type[EventT_co], handler: IEventHandler[SessionT_co, EventT_co], weak: bool = False
    ) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe(self, event_type: type[EventT_co], handler: IEventHandler[SessionT_co, EventT_co]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def add_pipeline(self, pipeline: IPipelineHandler[SessionT_co, CommandT_co]) -> None:
        raise NotImplementedError
