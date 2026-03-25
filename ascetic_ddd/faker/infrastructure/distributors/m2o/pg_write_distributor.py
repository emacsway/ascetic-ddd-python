import functools
import json
import typing
import dataclasses

from psycopg.types.json import Jsonb

from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.option import Option
from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.signals.signal import AsyncSignal
from ascetic_ddd.faker.domain.distributors.m2o.events import ValueAppendedEvent
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.infrastructure.session.pg_session import extract_internal_connection
from ascetic_ddd.faker.infrastructure.utils.json import JSONEncoder
from ascetic_ddd.utils import serializer
from ascetic_ddd.utils.pg import escape


__all__ = ('PgWriteDistributor',)


T = typing.TypeVar("T")


class PgWriteDistributor(IM2ODistributor[T], typing.Generic[T]):
    """Shared PG value storage for distributors.

    Stores values in a PostgreSQL table and always raises ICursor on next()
    (signals caller to create a new value).

    Multiple read distributors (PgWeightedDistributor, PgSkewDistributor)
    can share one PgWriteDistributor to see each other's values.

    Example::

        store = PgWriteDistributor()
        employee_dist = PgWeightedDistributor(store=store, weights=[0.9, 0.5], mean=5)
        device_dist = PgWeightedDistributor(store=store, weights=[0.3, 0.2], mean=20)
        # Both read from the same PG table
    """
    _extract_connection = staticmethod(extract_internal_connection)
    _initialized: bool = False
    _values_table: str | None = None
    _provider_name: str | None = None
    _on_appended: IAsyncSignal[ValueAppendedEvent[T]]

    def __init__(self):
        self._on_appended = AsyncSignal[ValueAppendedEvent[T]]()

    @property
    def on_appended(self) -> IAsyncSignal[ValueAppendedEvent[T]]:
        return self._on_appended

    async def next(
            self,
            session: ISession,
            specification: ISpecification[T],
    ) -> Option[T]:
        raise Cursor(
            position=-1,
            callback=self._append,
        )

    async def _append(self, session: ISession, value: T, position: int) -> None:
        if not self._initialized:
            await self.setup(session)
        sql = """
            INSERT INTO %(values_table)s (value, object)
            VALUES (%%s, %%s)
            ON CONFLICT DO NOTHING;
        """ % {
            'values_table': self._values_table,
        }
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(sql, (self._encode(value), self._serialize(value)))

        await self._on_appended.notify(ValueAppendedEvent(session, value, position))

    async def append(self, session: ISession, value: T):
        await self._append(session, value, -1)

    @property
    def values_table(self) -> str | None:
        return self._values_table

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        if self._provider_name is None:
            self._provider_name = value
            if self._values_table is None:
                self._values_table = escape("values_for_%s" % value[-(63 - 11):])

    async def setup(self, session: ISession):
        if not self._initialized:  # Fixes diamond problem
            if not (await self._is_initialized(session)):
                await self._setup(session)
            self._initialized = True

    async def _setup(self, session: ISession):
        sql = """
            CREATE TABLE IF NOT EXISTS %(values_table)s (
                position serial NOT NULL PRIMARY KEY,
                value JSONB NOT NULL,
                object TEXT NOT NULL,
                UNIQUE (value)
            );
            CREATE INDEX IF NOT EXISTS %(index_name)s ON %(values_table)s USING GIN(value jsonb_path_ops);
        """ % {
            "values_table": self._values_table,
            "index_name": escape("gin_%s" % self.provider_name[-(63 - 4):]),  # pyright: ignore[reportOptionalSubscript]
        }
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(sql)

    async def cleanup(self, session: ISession):
        if self._initialized:
            self._initialized = False
            async with self._extract_connection(session).cursor() as acursor:
                await acursor.execute("DROP TABLE IF EXISTS %s" % self._values_table)

    async def _is_initialized(self, session: ISession) -> bool:
        sql = """SELECT to_regclass(%s)"""
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(sql, (self._values_table,))
            regclass = (await acursor.fetchone())[0]  # type: ignore[index]
        return regclass is not None

    @staticmethod
    def _encode(obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            obj = dataclasses.asdict(obj)
        dumps = functools.partial(json.dumps, cls=JSONEncoder)
        return Jsonb(obj, dumps)

    _serialize = staticmethod(serializer.serialize)
    _deserialize = staticmethod(serializer.deserialize)

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self
