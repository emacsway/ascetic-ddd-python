import functools
import json
from abc import ABCMeta, abstractmethod

from psycopg.types.json import Jsonb

from ascetic_ddd.kms.interfaces import IKeyManagementService
from ascetic_ddd.seedwork.infrastructure.repository.stream_id import StreamId
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.session.pg_session import extract_connection

__all__ = ("IDekStore", "PgDekStore")

from ascetic_ddd.utils.json import JSONEncoder


class IDekStore(metaclass=ABCMeta):

    @abstractmethod
    async def get_or_create(self, session: ISession, stream_id: StreamId) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def get(self, session: ISession, stream_id: StreamId) -> bytes:
        raise NotImplementedError


class PgDekStore(IDekStore):
    _extract_connection = staticmethod(extract_connection)
    _table = "stream_deks"

    _select_sql = """
        SELECT encrypted_dek FROM stream_deks
        WHERE tenant_id = %s AND stream_type = %s AND stream_id = %s
    """
    _insert_sql = """
        INSERT INTO stream_deks (tenant_id, stream_type, stream_id, encrypted_dek)
        VALUES (%s, %s, %s, %s)
    """
    _create_table_sql = """
        CREATE TABLE IF NOT EXISTS %s (
            tenant_id varchar(128) NOT NULL,
            stream_type varchar(128) NOT NULL,
            stream_id jsonb NOT NULL,
            encrypted_dek bytea NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT %s_pk PRIMARY KEY (tenant_id, stream_type, stream_id)
        )
    """

    def __init__(self, kms: IKeyManagementService) -> None:
        self._kms = kms

    async def get_or_create(self, session: ISession, stream_id: StreamId) -> bytes:
        try:
            return await self.get(session, stream_id)
        except KeyError:
            dek, encrypted_dek = await self._kms.generate_dek(
                session, stream_id.tenant_id
            )
            await self._insert(session, stream_id, encrypted_dek)
            return dek

    async def get(self, session: ISession, stream_id: StreamId) -> bytes:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._select_sql, [
                stream_id.tenant_id, stream_id.stream_type, self._encode(stream_id.stream_id),
            ])
            row = await acursor.fetchone()
        if row is None:
            raise KeyError(stream_id)
        return await self._kms.decrypt_dek(session, stream_id.tenant_id, row[0])

    async def _insert(self, session: ISession, stream_id: StreamId, encrypted_dek: bytes) -> None:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._insert_sql, [
                stream_id.tenant_id, stream_id.stream_type, self._encode(stream_id.stream_id),
                encrypted_dek,
            ])

    @staticmethod
    def _encode(obj):
        dumps = functools.partial(json.dumps, cls=JSONEncoder)
        return Jsonb(obj, dumps)

    async def setup(self, session: ISession) -> None:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(
                self._create_table_sql % (self._table, self._table)
            )

    async def cleanup(self, session: ISession) -> None:
        pass
