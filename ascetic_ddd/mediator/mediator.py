import collections
import typing

from ascetic_ddd.mediator.interfaces import IRequestHandler, IEventHandler, IMediator, IPipelineHandler, IRequest
from ascetic_ddd.disposable.interfaces import IDisposable
from ascetic_ddd.disposable.disposable import Disposable

__all__ = ("Mediator",)

SessionT = typing.TypeVar("SessionT")
EventT = typing.TypeVar("EventT")
ResultT = typing.TypeVar("ResultT")


class Mediator(IMediator[SessionT], typing.Generic[SessionT]):
    def __init__(self) -> None:
        self._subscribers: collections.defaultdict[type, set] = collections.defaultdict(set)
        self._handlers: dict[type, typing.Any] = {}
        self._broadcast_pipelines: list = []
        self._pipelines: collections.defaultdict[type, list] = collections.defaultdict(list)

    async def send(self, session: SessionT, request: IRequest[ResultT]) -> ResultT:
        if handler := self._handlers.get(type(request)):
            return await self._execute_pipelines(session, request, handler)
        return None

    async def register(
            self,
            request_type: type[IRequest[ResultT]],
            handler: IRequestHandler[SessionT, IRequest[ResultT], ResultT]
    ) -> IDisposable:
        self._handlers[request_type] = handler

        async def callback():
            await self.unregister(request_type)

        return Disposable(callback)

    async def unregister(self, request_type: type[IRequest[ResultT]]) -> None:
        self._handlers.pop(request_type)

    async def publish(self, session: SessionT, event: EventT) -> None:
        for handler in self._subscribers[type(event)]:
            await handler(session, event)

    async def subscribe(
            self,
            event_type: type[EventT],
            handler: IEventHandler[SessionT, EventT],
    ) -> IDisposable:
        self._subscribers[event_type].add(handler)

        async def callback():
            await self.unsubscribe(event_type, handler)

        return Disposable(callback)

    async def unsubscribe(self, event_type: type[EventT], handler: IEventHandler[SessionT, EventT]) -> None:
        self._subscribers[event_type].discard(handler)

    async def add_pipeline(
            self,
            request_type: typing.Optional[type[IRequest[ResultT]]],
            pipeline: IPipelineHandler[SessionT, IRequest[ResultT], ResultT]
    ) -> None:
        if request_type is None:
            self._broadcast_pipelines.append(pipeline)
        else:
            self._pipelines[request_type].append(pipeline)

    async def _execute_pipelines(
            self, session: SessionT, request: typing.Any, handler: typing.Any
    ) -> typing.Any:

        current_handler = handler
        pipelines = self._broadcast_pipelines + self._pipelines.get(type(request), [])

        for pipeline in reversed(pipelines):
            current_handler = self._create_pipeline_handler(pipeline, current_handler)

        return await current_handler(session, request)

    @staticmethod
    def _create_pipeline_handler(
            pipeline: typing.Any,
            next_handler: typing.Any
    ) -> typing.Any:

        async def handler(session: typing.Any, request: typing.Any) -> typing.Any:
            return await pipeline(session, request, next_handler)

        return handler
