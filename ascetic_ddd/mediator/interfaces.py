import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.disposable.interfaces import IDisposable

__all__ = (
    "IMediator",
    "ICommandHandler",
    "IEventHandler",
    "IPipelineHandler",
    "ICommandResult",
)


ISession = typing.TypeVar("ISession", covariant=True)
ICommand = typing.TypeVar("ICommand", covariant=True)
IEvent = typing.TypeVar("IEvent", covariant=True)
ICommandResult = typing.TypeVar("ICommandResult")


class ICommandHandler(typing.Protocol[ISession, ICommand]):
    def __call__(self, session: ISession, command: ICommand) -> typing.Any:
        ...


class IEventHandler(typing.Protocol[ISession, IEvent]):
    def __call__(self, session: ISession, event: IEvent):
        ...


class IPipelineHandler(typing.Protocol[ISession, ICommand]):
    @abstractmethod
    async def __call__(
            self, session: ISession, command: ICommand, next_: 'ICommandHandler[ISession, ICommand]'
    ) -> typing.Any:
        ...


class IMediator(typing.Generic[ICommand, IEvent, ISession], metaclass=ABCMeta):

    @abstractmethod
    async def send(self, session: ISession, command: ICommand):
        raise NotImplementedError

    @abstractmethod
    async def register(self, command_type: type[ICommand], handler: ICommandHandler[ISession, ICommand]) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    async def unregister(self, command_type: type[ICommand]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def publish(self, session: ISession, event: IEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(
            self, event_type: type[IEvent], handler: IEventHandler[ISession, IEvent], weak: bool = False
    ) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe(self, event_type: type[IEvent], handler: IEventHandler[ISession, IEvent]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def add_pipeline(self, pipeline: IPipelineHandler[ISession, ICommand]) -> None:
        raise NotImplementedError
