import typing
import socket
import aiohttp
from contextlib import asynccontextmanager
from time import perf_counter

from aiohttp.client import ClientSession

from ascetic_ddd.session.identity_map import IdentityMap
from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.signals.signal import AsyncSignal
from ascetic_ddd.session.events import (
    SessionScopeStartedEvent,
    SessionScopeEndedEvent,
    RequestStartedEvent,
    RequestEndedEvent,
    RequestViewModel,
)
from ascetic_ddd.session.interfaces import ISession, IRestSession, IIdentityMap

__all__ = (
    "RestSession",
    "RestSessionPool",
    "extract_request",
)

_HOST = socket.gethostname()


def extract_request(session: ISession) -> ClientSession:
    return typing.cast(IRestSession, session).request


class RestSessionPool:
    _on_session_started: IAsyncSignal[SessionScopeStartedEvent]
    _on_session_ended: IAsyncSignal[SessionScopeEndedEvent]

    def __init__(self) -> None:
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
        _client_session = ClientSession()
        async with _client_session as client_session:
            session = self._make_session(client_session)
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
    def _make_session(client_session: ClientSession):
        return RestSession(client_session, IdentityMap(isolation_level=IdentityMap.READ_UNCOMMITTED))


class RestSession:
    # _client_session: httpx.AsyncClient
    _client_session: ClientSession
    _parent: typing.Optional["RestSession"]
    _identity_map: IIdentityMap
    _on_atomic_started: IAsyncSignal[SessionScopeStartedEvent]
    _on_atomic_ended: IAsyncSignal[SessionScopeEndedEvent]
    _on_request_started: IAsyncSignal[RequestStartedEvent]
    _on_request_ended: IAsyncSignal[RequestEndedEvent]

    def __init__(
            self,
            client_session: ClientSession,
            identity_map: IIdentityMap
    ):
        self._attach_observers_to_client(client_session)
        self._client_session = client_session
        self._parent = None
        self._identity_map = identity_map
        self._on_atomic_started = AsyncSignal[SessionScopeStartedEvent]()
        self._on_atomic_ended = AsyncSignal[SessionScopeEndedEvent]()
        self._on_request_started = AsyncSignal[RequestStartedEvent]()
        self._on_request_ended = AsyncSignal[RequestEndedEvent]()

    def _attach_observers_to_client(self, client: ClientSession):
        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(self._on_request_start)
        trace_config.on_request_end.append(self._on_request_end)
        trace_config.freeze()
        client.trace_configs.append(trace_config)

    @property
    def identity_map(self) -> IIdentityMap:
        return self._identity_map

    @property
    def on_atomic_started(self) -> IAsyncSignal[SessionScopeStartedEvent]:
        return self._on_atomic_started

    @property
    def on_atomic_ended(self) -> IAsyncSignal[SessionScopeEndedEvent]:
        return self._on_atomic_ended

    @property
    def on_request_started(self) -> IAsyncSignal[RequestStartedEvent]:
        return self._on_request_started

    @property
    def on_request_ended(self) -> IAsyncSignal[RequestEndedEvent]:
        return self._on_request_ended

    async def _on_request_start(self, session, context, params):
        prefix = "ascetic-ddd.%(hostname)s.%(method)s.%(host)s.%(path)s"
        data = {
            "method": params.method,
            "hostname": _HOST,
            "host": params.url.host,
            "path": params.url.path,
        }
        context._request_view = RequestViewModel(
            time_start=perf_counter(),  # asyncio.get_event_loop().time()
            label=prefix % data,
            status=None,
            response_time=None,
        )

        await self._on_request_started.notify(
            RequestStartedEvent(
                session=self,
                sender=context,
                request_view=context._request_view,
            )
        )

    async def _on_request_end(self, session, context, params):
        request_view = context._request_view

        # response_time = asyncio.get_event_loop().time() - request_view.time_start
        response_time = perf_counter() - request_view.time_start
        request_view.status = params.response.status
        request_view.response_time = response_time

        await self._on_request_ended.notify(
            RequestEndedEvent(
                session=self,
                sender=context,
                request_view=request_view,
            )
        )

    @asynccontextmanager
    async def atomic(self) -> typing.AsyncIterator[ISession]:
        trace_config = self._client_session.trace_configs.pop()
        atomic_session = self._make_atomic_session(self._client_session)
        await self._on_atomic_started.notify(
            SessionScopeStartedEvent(session=atomic_session)
        )
        try:
            yield atomic_session
        finally:
            if self._parent is None:
                atomic_session.identity_map.clear()
            await self._on_atomic_ended.notify(
                SessionScopeEndedEvent(session=atomic_session)
            )
            _ = self._client_session.trace_configs.pop()
            self._client_session.trace_configs.append(trace_config)

    @property
    # def request(self) -> httpx.AsyncClient:
    def request(self) -> ClientSession:
        return self._client_session

    def _make_atomic_session(self, client_session: ClientSession) -> IRestSession:
        return RestAtomicSession(client_session, IdentityMap(), self)


class RestAtomicSession(RestSession):

    def __init__(
            self,
            client_session: ClientSession,
            identity_map: IIdentityMap,
            parent: typing.Optional["RestSession"]
    ):
        super().__init__(client_session, identity_map)
        self._parent = parent

    def _make_atomic_session(self, client_session: ClientSession) -> IRestSession:
        return RestAtomicSession(client_session, self._identity_map, self)
