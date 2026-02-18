import typing
import weakref
from contextlib import asynccontextmanager
from time import perf_counter
from types import TracebackType
# from psycopg import AsyncConnection

from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.signals.signal import AsyncSignal
from ascetic_ddd.session.events import (
    QueryStartedEvent,
    QueryEndedEvent,
    SessionScopeStartedEvent,
    SessionScopeEndedEvent,
)
from ascetic_ddd.session.interfaces import (
    ISession,
    IPgSession,
    IIdentityMap,
    IAsyncConnection,
    IAsyncConnectionPool,
    IAsyncCursor,
    Query,
    Params
)
from ascetic_ddd.session.identity_map import IdentityMap

__all__ = (
    "PgSession",
    "PgSessionPool",
    "PgAtomicSession",
    "extract_connection",
    "AsyncCursorStatsDecorator",
    "AsyncConnectionStatsDecorator",
)


def extract_connection(session: ISession) -> IAsyncConnection[tuple[typing.Any, ...]]:
    return typing.cast(IPgSession, session).connection


class PgSessionPool:
    _pool: IAsyncConnectionPool[tuple[typing.Any, ...]]
    _on_session_started: IAsyncSignal[SessionScopeStartedEvent]
    _on_session_ended: IAsyncSignal[SessionScopeEndedEvent]

    def __init__(self, pool: IAsyncConnectionPool[tuple[typing.Any, ...]]) -> None:
        self._pool = pool
        self._on_session_started = AsyncSignal[SessionScopeStartedEvent]()
        self._on_session_ended = AsyncSignal[SessionScopeEndedEvent]()

    @property
    def on_session_started(self) -> IAsyncSignal[SessionScopeStartedEvent]:
        return self._on_session_started

    @property
    def on_session_ended(self) -> IAsyncSignal[SessionScopeEndedEvent]:
        return self._on_session_ended

    @asynccontextmanager
    async def session(self) -> typing.AsyncIterator[ISession]:
        async with self._pool.connection() as conn:
            # await conn.set_isolation_level(IsolationLevel.READ_COMMITTED)
            session = self._make_session(conn)
            await self._on_session_started.notify(
                SessionScopeStartedEvent(session=session)
            )
            try:
                yield session
            finally:
                await self._on_session_ended.notify(
                    SessionScopeEndedEvent(session=session)
                )

    @staticmethod
    def _make_session(connection: IAsyncConnection[tuple[typing.Any, ...]]) -> 'ISession':
        return PgSession(connection)


class PgSession:
    _connection: IAsyncConnection[tuple[typing.Any, ...]]
    _parent: typing.Optional["IPgSession"]
    _identity_map: IIdentityMap
    _on_started: IAsyncSignal[SessionScopeStartedEvent]
    _on_ended: IAsyncSignal[SessionScopeEndedEvent]
    _on_query_started: IAsyncSignal[QueryStartedEvent]
    _on_query_ended: IAsyncSignal[QueryEndedEvent]

    def __init__(
            self,
            connection: IAsyncConnection[tuple[typing.Any, ...]],
            parent: typing.Optional["IPgSession"] = None
    ):
        # self._connection = connection
        self._connection = AsyncConnectionStatsDecorator(connection, self)
        self._parent = parent
        self._identity_map = IdentityMap(isolation_level=IdentityMap.READ_UNCOMMITTED)
        self._on_started = AsyncSignal[SessionScopeStartedEvent]()
        self._on_ended = AsyncSignal[SessionScopeEndedEvent]()
        self._on_query_started = AsyncSignal[QueryStartedEvent]()
        self._on_query_ended = AsyncSignal[QueryEndedEvent]()

    @property
    def connection(self) -> IAsyncConnection[tuple[typing.Any, ...]]:
        return self._connection

    @property
    def identity_map(self) -> IIdentityMap:
        return self._identity_map

    @property
    def on_started(self) -> IAsyncSignal[SessionScopeStartedEvent]:
        return self._on_started

    @property
    def on_ended(self) -> IAsyncSignal[SessionScopeEndedEvent]:
        return self._on_ended

    @property
    def on_query_started(self) -> IAsyncSignal[QueryStartedEvent]:
        return self._on_query_started

    @property
    def on_query_ended(self) -> IAsyncSignal[QueryEndedEvent]:
        return self._on_query_ended

    @asynccontextmanager
    async def atomic(self) -> typing.AsyncIterator[ISession]:
        async with self.connection.transaction() as transaction:
            atomic_session = self._make_atomic_session(transaction.connection)
            await self._on_started.notify(
                SessionScopeStartedEvent(session=atomic_session)
            )
            try:
                yield atomic_session
            finally:
                await self._on_ended.notify(
                    SessionScopeEndedEvent(session=atomic_session)
                )

    def _make_atomic_session(self, connection: IAsyncConnection[tuple[typing.Any, ...]]) -> IPgSession:
        return PgAtomicSession(connection, IdentityMap(), self)


class PgAtomicSession(PgSession):

    def __init__(
            self,
            connection: IAsyncConnection[tuple[typing.Any, ...]],
            identity_map: IIdentityMap,
            parent: typing.Optional["IPgSession"] = None
    ):
        super().__init__(connection, parent)
        self._identity_map = identity_map

    def _make_atomic_session(self, connection: IAsyncConnection[tuple[typing.Any, ...]]) -> IPgSession:
        return PgAtomicSession(connection, self._identity_map, self)


class AsyncCursorStatsDecorator:
    _delegate: IAsyncCursor
    _session: weakref.ReferenceType[IPgSession]

    def __init__(self, delegate: IAsyncCursor, session: IPgSession):
        self._delegate = delegate
        self._session = weakref.ref(session)

    async def execute(
        self,
        query: Query,
        params: Params | None = None,
        *,
        prepare: bool | None = None,
        binary: bool | None = None,
    ):
        session = self._session()
        await session.on_query_started.notify(
            QueryStartedEvent(
                query=query,
                params=params,
                sender=self,
                session=session,
            )
        )
        time_start = perf_counter()
        await self._delegate.execute(query, params, prepare=prepare, binary=binary)
        response_time = perf_counter() - time_start
        await session.on_query_ended.notify(
            QueryEndedEvent(
                query=query,
                params=params,
                sender=self,
                session=session,
                response_time=response_time,
            )
        )
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._delegate.__aexit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name):
        return getattr(self._delegate, name)


class AsyncConnectionStatsDecorator:
    _delegate: IAsyncConnection
    _session: weakref.ReferenceType[IPgSession]

    def __init__(self, delegate: IAsyncConnection, session: IPgSession):
        self._delegate = delegate
        self._session = weakref.ref(session)

    def cursor(self, *a, **kw):
        return AsyncCursorStatsDecorator(self._delegate.cursor(*a, **kw), self._session())

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._delegate.__aexit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name):
        return getattr(self._delegate, name)
