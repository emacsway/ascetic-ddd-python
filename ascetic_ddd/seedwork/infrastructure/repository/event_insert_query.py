import functools
import json
import typing
from abc import ABCMeta

from psycopg.types.json import Jsonb

from ascetic_ddd.seedwork.domain.aggregate import (
    EventMeta,
    EventMetaExporter,
)
from ascetic_ddd.seedwork.infrastructure.repository import StreamId
from ascetic_ddd.seedwork.infrastructure.repository.interfaces import IEventInsertQuery, ICodecFactory
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.session.pg_session import extract_connection
from ascetic_ddd.utils.json import JSONEncoder

__all__ = ("EventInsertQuery",)


class EventInsertQuery(IEventInsertQuery, metaclass=ABCMeta):
    _extract_connection = staticmethod(extract_connection)
    # TODO: add occurred_at column to table for partitioning reason? created_at with default = NOW()
    _sql = """
        INSERT INTO event_log
        (tenant_id, stream_type, stream_id, stream_position, event_type, event_version, payload, metadata)
        VALUES
        (%s, %s, %s, %s, %s, %s, %s)
    """

    def __init__(self) -> None:
        self.data = {}
        self._params: list[typing.Any] = [None] * 8
        self._params[0] = 1  # default tenant
        self._metadata = {}
        super().__init__()

    def set_tenant_id(self, value: typing.Any) -> None:
        """
        aggregate.id.tenant_id
        """
        self._params[0] = value

    def set_stream_type(self, value: str) -> None:
        """
        bounded_context_name.aggregate_name
        """
        self._params[1] = value

    def set_stream_id(self, value: typing.Any) -> None:
        """
        aggregate.id.internal_id
        Use JsonB to store
        """
        self._params[2] = value

    def set_aggregate_version(self, value: int) -> None:
        self._params[3] = value

    def set_event_type(self, value: str) -> None:
        self._params[4] = value

    def set_event_version(self, value: int) -> None:
        self._params[5] = value

    def set_event_meta(self, meta: EventMeta) -> None:
        exporter = EventMetaExporter()
        meta.export(exporter)
        self._params[7] = self._encode(exporter.data)

    async def evaluate(self, codec_factory: ICodecFactory, session: ISession) -> None:
        codec = await codec_factory(session, StreamId(*self._params[:3]))
        self._params[6] = codec.encode(self.data)
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._sql, self._params)

    @staticmethod
    def _encode(obj):
        dumps = functools.partial(json.dumps, cls=JSONEncoder)
        return Jsonb(obj, dumps)
