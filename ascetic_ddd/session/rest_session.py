import dataclasses
import typing
import socket
import aiohttp
from contextlib import asynccontextmanager
from time import perf_counter

from aiohttp.client import ClientSession

from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.signals.signal import AsyncSignal
from ascetic_ddd.session.events import (
    SessionScopeStartedEvent,
    SessionScopeEndedEvent,
    RequestStartedEvent,
    RequestEndedEvent,
)
from ascetic_ddd.session.interfaces import ISession, IRestSession

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
        session = self._make_session()
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
    def _make_session():
        return RestSession()


class RestSession:
    # _client_session: httpx.AsyncClient
    _client_session: ClientSession
    _parent: typing.Optional["RestSession"]
    _on_started: IAsyncSignal[SessionScopeStartedEvent]
    _on_ended: IAsyncSignal[SessionScopeEndedEvent]
    _on_request_started: IAsyncSignal[RequestStartedEvent]
    _on_request_ended: IAsyncSignal[RequestEndedEvent]

    @dataclasses.dataclass(kw_only=True)
    class RequestViewModel:
        time_start: float
        label: str
        status: int | None
        response_time: float | None

        def __str__(self):
            return self.label + "." + str(self.status)

    def __init__(self, client_session: ClientSession | None = None, parent: typing.Optional["RestSession"] = None):
        self._parent = parent
        self._on_started = AsyncSignal[SessionScopeStartedEvent]()
        self._on_ended = AsyncSignal[SessionScopeEndedEvent]()
        self._on_request_started = AsyncSignal[RequestStartedEvent]()
        self._on_request_ended = AsyncSignal[RequestEndedEvent]()

        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(self._on_request_start)
        trace_config.on_request_end.append(self._on_request_end)
        self._client_session = client_session or ClientSession(trace_configs=[trace_config])

    @property
    def on_started(self) -> IAsyncSignal[SessionScopeStartedEvent]:
        return self._on_started

    @property
    def on_ended(self) -> IAsyncSignal[SessionScopeEndedEvent]:
        return self._on_ended

    @property
    def on_request_started(self) -> IAsyncSignal[RequestStartedEvent]:
        return self._on_request_started

    @property
    def on_request_ended(self) -> IAsyncSignal[RequestEndedEvent]:
        return self._on_request_ended

    async def _on_request_start(self, session, context, params):
        prefix = "performance-testing.%(hostname)s.%(method)s.%(host)s.%(path)s"
        data = {
            "method": params.method,
            "hostname": _HOST,
            "host": params.url.host,
            "path": params.url.path,
        }
        context._request_view = self.RequestViewModel(
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
        async with self._client_session as client_session:
            session = self._make_atomic_session(client_session)
            await self._on_started.notify(
                SessionScopeStartedEvent(session=session)
            )
            try:
                yield session
            finally:
                await self._on_ended.notify(
                    SessionScopeEndedEvent(session=session)
                )

    @property
    # def request(self) -> httpx.AsyncClient:
    def request(self) -> ClientSession:
        return self._client_session

    def _make_atomic_session(self, client_session: ClientSession) -> IRestSession:
        return RestAtomicSession(client_session, self)


class RestAtomicSession(RestSession):

    def __init__(self, client_session: ClientSession | None = None, parent: typing.Optional["RestSession"] = None):
        super().__init__(client_session, parent)

    @asynccontextmanager
    async def atomic(self) -> typing.AsyncIterator[ISession]:
        async with self._client_session as client_session:
            session = self._make_atomic_session(client_session)
            await self._on_started.notify(
                SessionScopeStartedEvent(session=session)
            )
            try:
                yield session
            finally:
                await self._on_ended.notify(
                    SessionScopeEndedEvent(session=session)
                )

    def _make_atomic_session(self, client_session: ClientSession) -> IRestSession:
        return RestAtomicSession(client_session, self)
