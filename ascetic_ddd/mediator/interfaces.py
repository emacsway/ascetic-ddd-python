import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.disposable.interfaces import IDisposable

__all__ = (
    "IRequest",
    "IMediator",
    "IRequestHandler",
    "IEventHandler",
    "IPipelineHandler",
)

SessionT = typing.TypeVar("SessionT")
RequestT = typing.TypeVar("RequestT")
EventT = typing.TypeVar("EventT")
ResultT = typing.TypeVar("ResultT")

SessionT_contra = typing.TypeVar("SessionT_contra", contravariant=True)
RequestT_contra = typing.TypeVar("RequestT_contra", contravariant=True)
EventT_contra = typing.TypeVar("EventT_contra", contravariant=True)
ResultT_co = typing.TypeVar("ResultT_co", covariant=True)


class IRequest(typing.Generic[ResultT]):
    pass


class IRequestHandler(typing.Protocol[SessionT_contra, RequestT_contra, ResultT_co]):
    def __call__(self, session: SessionT_contra, request: RequestT_contra) -> ResultT_co:
        ...


class IEventHandler(typing.Protocol[SessionT_contra, EventT_contra]):
    def __call__(self, session: SessionT_contra, event: EventT_contra):
        ...


class IPipelineHandler(typing.Protocol[SessionT_contra, RequestT_contra, ResultT]):
    @abstractmethod
    async def __call__(
            self, session: SessionT_contra, request: RequestT_contra,
            next_: typing.Callable[..., typing.Awaitable[ResultT]]
    ) -> ResultT:
        ...


class IMediator(typing.Generic[SessionT], metaclass=ABCMeta):

    @abstractmethod
    async def send(self, session: SessionT, request: IRequest[ResultT]) -> ResultT:
        raise NotImplementedError

    @abstractmethod
    async def register(
            self,
            request_type: type[IRequest[ResultT]],
            handler: IRequestHandler[SessionT, IRequest[ResultT], ResultT]
    ) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    async def unregister(self, request_type: type[IRequest[ResultT]]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def publish(self, session: SessionT, event: EventT) -> None:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(
            self,
            event_type: type[EventT],
            handler: IEventHandler[SessionT, EventT],
    ) -> IDisposable:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe(self, event_type: type[EventT], handler: IEventHandler[SessionT, EventT]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def add_pipeline(
            self,
            request_type: typing.Optional[type[IRequest[ResultT]]],
            pipeline: IPipelineHandler[SessionT, IRequest[ResultT], ResultT]
    ) -> None:
        raise NotImplementedError
