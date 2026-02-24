import typing
import uuid
from abc import ABCMeta
from dataclasses import dataclass, replace

import dateutil.parser

from ascetic_ddd.seedwork.domain.aggregate import (
    CausalDependency,
    EventMeta,
    PersistentDomainEvent,
)
from ascetic_ddd.seedwork.infrastructure.repository import ICodec
from ascetic_ddd.seedwork.infrastructure.repository.interfaces import IEventGetQuery, ICodecFactory
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.seedwork.infrastructure.repository.stream_id import StreamId
from ascetic_ddd.session.pg_session import extract_connection

__all__ = (
    "EventGetQuery",
    "Row",
)


class EventGetQuery(IEventGetQuery, metaclass=ABCMeta):
    _extract_connection = staticmethod(extract_connection)

    class Reconstitutors(dict):
        def register(self, event_type: type[PersistentDomainEvent], event_version: int):
            def do_register(
                reconstitutor: typing.Callable[["EventGetQuery", "Row"], PersistentDomainEvent]
            ):
                self[(event_type.__name__, event_version)] = reconstitutor
                return reconstitutor

            return do_register

    reconstitutors = Reconstitutors()

    """
    The query does not need tenant_id, stream_type, stream_id, since they are already known and serve as selection criteria.
    """
    _sql = """
        SELECT
            stream_position, event_type, event_version, payload, metadata
        FROM
            event_log
        WHERE
            tenant_id=%s AND stream_type = %s AND stream_id = %s AND stream_position > %s
        ORDER BY
            tenant_id, stream_type, stream_id, stream_position
    """

    def __init__(self, stream_id: StreamId, since_position: int = 0) -> None:
        self._stream_id = stream_id
        self._since_position = since_position

    async def evaluate(self, codec_factory: ICodecFactory, session: ISession) -> typing.Iterable[PersistentDomainEvent]:
        codec = await codec_factory(session, self._stream_id)
        async with self._extract_connection(session).cursor() as acursor:
            params = [self._stream_id.tenant_id, self._stream_id.stream_type,
                      self._stream_id.stream_id, self._since_position]
            await acursor.execute(self._sql, params)
            rows = await acursor.fetchall()
            return tuple(self._reconstitute_event(self._decode_row(codec, Row(*row))) for row in rows)

    def _decode_row(self, payload_codec: ICodec, row: 'Row') -> 'Row':
        return replace(row, payload=payload_codec.decode(bytes(row.payload)))

    def _reconstitute_event(self, row: "Row") -> PersistentDomainEvent:
        return self.reconstitutors[(row.event_type, row.event_version)](self, row)

    def _persistent_domain_event_kwargs(self, row: "Row") -> dict:
        return {
            "event_meta": self._reconstitute_event_meta(row.metadata),
            "aggregate_version": row.aggregate_version,
        }

    def _reconstitute_event_meta(self, data: dict) -> EventMeta:
        """Meta can be customised, thus, allow to reload this method"""

        def r(c, x):
            return x and c(x)

        return EventMeta(
            event_id=r(uuid.UUID, data.get("event_id")),
            causation_id=r(uuid.UUID, data.get("causation_id")),
            correlation_id=r(uuid.UUID, data.get("correlation_id")),
            reason=data.get("reason"),
            occurred_at=r(dateutil.parser.isoparse, data.get("occurred_at")),
            causal_dependencies=tuple(
                map(self._reconstitute_causal_dependency, data.get("causal_dependencies", []))
            ),
        )

    def _reconstitute_causal_dependency(self, data: dict) -> CausalDependency:
        return CausalDependency(
            tenant_id=data["tenant_id"],
            stream_id=data["aggregate_id"],
            stream_type=data["aggregate_type"],
            stream_position=data["aggregate_version"],
        )


@dataclass(frozen=True)
class Row:
    aggregate_version: int
    event_type: str
    event_version: int
    payload: dict
    metadata: dict
