import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.seedwork.domain.aggregate import IPersistentDomainEventExporter, PersistentDomainEvent
from ascetic_ddd.seedwork.infrastructure.repository import StreamId
from ascetic_ddd.session.interfaces import ISession


__all__ = (
    'ICodec',
    'ICodecFactory',
    'IDekStore',
    'IEventInsertQuery',
    'IEventGetQuery',
)


class ICodec(metaclass=ABCMeta):

    @abstractmethod
    def encode(self, obj: dict) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def decode(self, data: bytes) -> dict:
        raise NotImplementedError


ICodecFactory: typing.TypeAlias = typing.Callable[[ISession, StreamId], typing.Awaitable[ICodec]]


class IDekStore(metaclass=ABCMeta):

    @abstractmethod
    async def get_or_create(self, session: ISession, stream_id: StreamId) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def get(self, session: ISession, stream_id: StreamId) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, session: ISession, stream_id: StreamId) -> None:
        raise NotImplementedError


@abstractmethod
class IEventInsertQuery(IPersistentDomainEventExporter, metaclass=ABCMeta):

    @abstractmethod
    def set_stream_type(self, value: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def evaluate(self, codec_factory: ICodecFactory, session: ISession) -> None:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def make(cls, event: PersistentDomainEvent) -> "IEventInsertQuery":
        raise NotImplementedError


@abstractmethod
class IEventGetQuery(metaclass=ABCMeta):
    async def evaluate(self, codec_factory: ICodecFactory, session: ISession) -> typing.Iterable[PersistentDomainEvent]:
        raise NotImplementedError
