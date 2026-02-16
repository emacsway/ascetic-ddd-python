import collections
import typing
from weakref import WeakSet

from ascetic_ddd.mediator.interfaces import ICommandHandler, IEventHandler, IMediator, IPipelineHandler, CommandResultT
from ascetic_ddd.disposable.interfaces import IDisposable
from ascetic_ddd.disposable.disposable import Disposable

__all__ = ("Mediator",)

SessionT_co = typing.TypeVar("SessionT_co", covariant=True)
CommandT_co = typing.TypeVar("CommandT_co", covariant=True)
EventT_co = typing.TypeVar("EventT_co", covariant=True)


class Mediator(typing.Generic[CommandT_co, EventT_co, SessionT_co], IMediator[CommandT_co, EventT_co, SessionT_co]):
    def __init__(self) -> None:
        self._subscribers: collections.defaultdict[
            type[EventT_co], WeakSet[IEventHandler[SessionT_co, EventT_co]]
        ] = collections.defaultdict(
            WeakSet
        )
        self._weak_cache: set[IEventHandler[SessionT_co, EventT_co]] = set()
        self._handlers: dict[type[CommandT_co], ICommandHandler[SessionT_co, CommandT_co]] = {}
        self._pipelines: list[IPipelineHandler[SessionT_co, CommandT_co, CommandResultT]] = []

    async def send(self, session: SessionT_co, command: CommandT_co) -> typing.Optional[CommandResultT]:
        if handler := self._handlers.get(type(command)):
            return await self._execute_pipelines(session, command, handler)
        return None

    async def register(self, command_type: type[CommandT_co], handler: ICommandHandler[SessionT_co, CommandT_co]) -> IDisposable:
        self._handlers[command_type] = handler

        async def callback():
            await self.unregister(command_type)

        return Disposable(callback)

    async def unregister(self, command_type: type[CommandT_co]) -> None:
        self._handlers.pop(command_type)

    async def publish(self, session: SessionT_co, event: EventT_co) -> None:
        for handler in self._subscribers[type(event)]:
            await handler(session, event)

    async def subscribe(
            self, event_type: type[EventT_co], handler: IEventHandler[SessionT_co, EventT_co], weak: bool = False
    ) -> IDisposable:
        self._subscribers[event_type].add(handler)
        if not weak:
            self._weak_cache.add(handler)

        async def callback():
            await self.unsubscribe(event_type, handler)

        return Disposable(callback)

    async def unsubscribe(self, event_type: type[EventT_co], handler: IEventHandler[SessionT_co, EventT_co]) -> None:
        self._subscribers[event_type].discard(handler)
        self._weak_cache.discard(handler)

    async def add_pipeline(self, pipeline: IPipelineHandler[SessionT_co, CommandT_co]) -> None:
        self._pipelines.append(pipeline)

    async def _execute_pipelines(
            self, session: SessionT_co, command: CommandT_co, handler: ICommandHandler[SessionT_co, CommandT_co]
    ) -> typing.Any:

        current_handler = handler

        for pipeline in reversed(self._pipelines):
            current_handler = self._create_pipeline_handler(pipeline, current_handler)

        return await current_handler(session, command)

    @staticmethod
    def _create_pipeline_handler(
            pipeline: IPipelineHandler[SessionT_co, CommandT_co],
            next_handler: ICommandHandler[SessionT_co, CommandT_co]
    ) -> ICommandHandler[SessionT_co, CommandT_co]:

        async def handler(session: SessionT_co, command: CommandT_co) -> typing.Any:
            return await pipeline(session, command, next_handler)

        return handler
