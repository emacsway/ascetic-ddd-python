import dataclasses
import typing
import uuid
from abc import ABCMeta

from psycopg.errors import UniqueViolation

from ascetic_ddd.kms.models import Aes256GcmCipher
from ascetic_ddd.mediator.interfaces import IMediator
from ascetic_ddd.seedwork.infrastructure.repository.codec import (
    EncryptionCodec,
    JsonCodec,
    ZlibCodec,
)
from ascetic_ddd.seedwork.infrastructure.repository.interfaces import (
    ICodecFactory,
    ICodec,
    IDekStore,
    IEventInsertQuery,
)
from ascetic_ddd.seedwork.infrastructure.repository.stream_id import StreamId
from ascetic_ddd.session.exceptions import ConcurrentUpdate
from ascetic_ddd.seedwork.domain.aggregate import (
    EventMeta,
    IDomainEventAccessor,
    PersistentDomainEvent,
)
from ascetic_ddd.session.interfaces import ISession

___all__ = ("EventStore",)


IPDE = typing.TypeVar("IPDE", bound=PersistentDomainEvent, covariant=True)


class EventStore(typing.Generic[IPDE], metaclass=ABCMeta):
    class Queries(dict):
        def register(self, event_type: type[PersistentDomainEvent], event_version: int):
            def do_register(query_cls: type[IEventInsertQuery]):
                self[(event_type.__name__, event_version)] = query_cls
                return query_cls

            return do_register

    queries = Queries()

    _stream_type: str
    _mediator: IMediator

    def __init__(self, dek_store: IDekStore, mediator: IMediator) -> None:
        self._dek_store = dek_store
        self._mediator = mediator

    async def _save(
        self,
        session: ISession,
        agg: IDomainEventAccessor[IPDE],
        event_meta: EventMeta,
    ) -> None:
        events = []
        pending_events = agg.pending_domain_events
        del agg.pending_domain_events

        codec_factory = await self._make_codec_factory()

        causation_id = None
        for event in pending_events:
            event_id = uuid.uuid4()
            event_meta = dataclasses.replace(
                event_meta, event_id=event_id, causation_id=causation_id
            )
            causation_id = event_id
            event = dataclasses.replace(event, event_meta=event_meta)
            query = self._do_make_event_query(event)
            query.set_stream_type(self._stream_type)
            try:
                await query.evaluate(codec_factory, session)
            except UniqueViolation as e:
                raise ConcurrentUpdate(query) from e
            events.append(event)

        for event in events:
            await self._mediator.publish(event, session)

    async def _make_codec_factory(self) -> ICodecFactory:
        _cache = {}

        async def codec_factory(session: ISession, stream_id: StreamId) -> ICodec:
            if stream_id not in _cache:
                dek = await self._dek_store.get_or_create(session, stream_id)
                aad = str(stream_id).encode("utf-8")
                cipher = Aes256GcmCipher(dek, aad)
                _cache[stream_id] = EncryptionCodec(cipher, ZlibCodec(JsonCodec()))
            return _cache[stream_id]

        return codec_factory

    def _do_make_event_query(self, event: IPDE) -> IEventInsertQuery:
        return self.queries[(event.event_type, event.event_version)].make(event)
