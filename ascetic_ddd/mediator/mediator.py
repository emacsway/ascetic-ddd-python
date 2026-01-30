import collections
import typing
from weakref import WeakSet

from ascetic_ddd.mediator.interfaces import ICommandHandler, IEventHandler, IMediator, IPipelineHandler, ICommandResult
from ascetic_ddd.disposable.interfaces import IDisposable
from ascetic_ddd.disposable.disposable import Disposable

__all__ = ("Mediator",)

ISession = typing.TypeVar("ISession", covariant=True)
ICommand = typing.TypeVar("ICommand", covariant=True)
IEvent = typing.TypeVar("IEvent", covariant=True)


class Mediator(typing.Generic[ICommand, IEvent, ISession], IMediator[ICommand, IEvent, ISession]):
    def __init__(self) -> None:
        self._subscribers: collections.defaultdict[
            type[IEvent], WeakSet[IEventHandler[ISession, IEvent]]
        ] = collections.defaultdict(
            WeakSet
        )
        self._weak_cache: set[IEventHandler[ISession, IEvent]] = set()
        self._handlers: dict[type[ICommand], ICommandHandler[ISession, ICommand]] = {}
        self._pipelines: list[IPipelineHandler[ISession, ICommand, ICommandResult]] = []

    async def send(self, session: ISession, command: ICommand) -> typing.Optional[ICommandResult]:
        if handler := self._handlers.get(type(command)):
            return await self._execute_pipelines(session, command, handler)
        return None

    async def register(self, command_type: type[ICommand], handler: ICommandHandler[ISession, ICommand]) -> IDisposable:
        self._handlers[command_type] = handler

        async def callback():
            await self.unregister(command_type)

        return Disposable(callback)

    async def unregister(self, command_type: type[ICommand]) -> None:
        self._handlers.pop(command_type)

    async def publish(self, session: ISession, event: IEvent) -> None:
        for handler in self._subscribers[type(event)]:
            await handler(session, event)

    async def subscribe(
            self, event_type: type[IEvent], handler: IEventHandler[ISession, IEvent], weak: bool = False
    ) -> IDisposable:
        self._subscribers[event_type].add(handler)
        if not weak:
            self._weak_cache.add(handler)

        async def callback():
            await self.unsubscribe(event_type, handler)

        return Disposable(callback)

    async def unsubscribe(self, event_type: type[IEvent], handler: IEventHandler[ISession, IEvent]) -> None:
        self._subscribers[event_type].discard(handler)
        self._weak_cache.discard(handler)

    async def add_pipeline(self, pipeline: IPipelineHandler[ISession, ICommand]) -> None:
        self._pipelines.append(pipeline)

    async def _execute_pipelines(
            self, session: ISession, command: ICommand, handler: ICommandHandler[ISession, ICommand]
    ) -> typing.Any:

        current_handler = handler

        for pipeline in reversed(self._pipelines):
            current_handler = self._create_pipeline_handler(pipeline, current_handler)

        return await current_handler(session, command)

    @staticmethod
    def _create_pipeline_handler(
            pipeline: IPipelineHandler[ISession, ICommand],
            next_handler: ICommandHandler[ISession, ICommand]
    ) -> ICommandHandler[ISession, ICommand]:

        async def handler(session: ISession, command: ICommand) -> typing.Any:
            return await pipeline(session, command, next_handler)

        return handler
