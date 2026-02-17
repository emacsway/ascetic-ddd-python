import typing
from contextlib import asynccontextmanager

from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.signals.signal import AsyncSignal
from ascetic_ddd.session.events import SessionScopeStartedEvent, SessionScopeEndedEvent, QueryStartedEvent, \
    QueryEndedEvent
from ascetic_ddd.session.interfaces import (
    ISession,
    IPgSession,
    IIdentityMap,
    IAsyncConnection
)
from ascetic_ddd.session.identity_map import IdentityMap
from ascetic_ddd.session.pg_session import AsyncConnectionStatsDecorator
from tortoise.transactions import in_transaction
from tortoise import BaseDBAsyncClient

__all__ = (
    "TortoiseSession",
    "TortoiseSessionPool",
    "extract_client",
)


def extract_client(session: IPgSession) -> BaseDBAsyncClient:
    return session.client


class TortoiseSessionPool:
    _connection_name: typing.Optional[str]
    _on_session_started: IAsyncSignal[SessionScopeStartedEvent]
    _on_session_ended: IAsyncSignal[SessionScopeEndedEvent]

    def __init__(self, connection_name: typing.Optional[str] = None) -> None:
        self._connection_name = connection_name
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
        """
        We have to open the session already here. Technically, the connection could be acquired via acquire_connection(),
        but BaseDBAsyncClient cannot work with an already acquired connection and will acquire it again.
        This would cause connections to be used twice.
        Therefore, either TortoiseSession.connection() should raise NotImplementedError,
        or the transaction should be started at session creation time.
        The second option is fully backward compatible.
        """
        async with in_transaction(self._connection_name) as client:
            session = self._make_session(client)
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
    def _make_session(client: BaseDBAsyncClient):
        return TortoiseSession(client)


class TortoiseSession:
    _client: BaseDBAsyncClient
    _parent: typing.Optional["TortoiseSession"]
    _identity_map: IIdentityMap
    _on_started: IAsyncSignal[SessionScopeStartedEvent]
    _on_ended: IAsyncSignal[SessionScopeEndedEvent]

    def __init__(
            self,
            client: BaseDBAsyncClient,
            parent: typing.Optional["TortoiseSession"] = None
    ):
        self._client = client
        self._parent = parent
        self._identity_map = IdentityMap()
        self._on_started = AsyncSignal[SessionScopeStartedEvent]()
        self._on_ended = AsyncSignal[SessionScopeEndedEvent]()
        self._on_query_started = AsyncSignal[QueryStartedEvent]()
        self._on_query_ended = AsyncSignal[QueryEndedEvent]()

    @property
    def connection(self) -> IAsyncConnection[typing.Any]:
        return AsyncConnectionStatsDecorator(self._client._connection, self)

    @property
    def client(self) -> BaseDBAsyncClient:
        return self._client

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
        async with self._client._in_transaction() as transactional_client:
            atomic_session = self._make_atomic_session(transactional_client)
            await self._on_started.notify(
                SessionScopeStartedEvent(session=atomic_session)
            )
            try:
                yield atomic_session
            finally:
                await self._on_ended.notify(
                    SessionScopeEndedEvent(session=atomic_session)
                )

    def _make_atomic_session(self, client):
        return TortoiseAtomicSession(client, self._identity_map, self)


class TortoiseAtomicSession(TortoiseSession):

    def __init__(
            self,
            client: BaseDBAsyncClient,
            identity_map: IIdentityMap,
            parent: typing.Optional["TortoiseSession"] = None
    ):
        super().__init__(client, parent)
        self._identity_map = identity_map

    def _make_atomic_session(self, client):
        return TortoiseAtomicSession(client, self._identity_map, self)
