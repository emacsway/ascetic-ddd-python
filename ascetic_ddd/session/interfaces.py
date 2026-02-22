import typing

from abc import ABCMeta, abstractmethod
from collections.abc import Hashable
from dataclasses import dataclass
from types import TracebackType

from aiohttp import ClientSession
from typing_extensions import TypeVar

from ascetic_ddd.session.events import (
    SessionScopeStartedEvent,
    SessionScopeEndedEvent,
    QueryStartedEvent,
    QueryEndedEvent,
    RequestStartedEvent,
    RequestEndedEvent,
)
from ascetic_ddd.signals.interfaces import IAsyncSignal


__all__ = (
    "Query",
    "Params",
    "TupleRow",
    "Row",
    "IAsyncConnection",
    "IAsyncConnectionPool",
    "IAsyncCursor",
    "IAsyncTransaction",
    "ISession",
    "ISessionPool",
    "IIdentityMap",
    "IdentityKey",
    "IPgSession",
    "IRestSession",
)


# Domain layer interfaces:


class ISession(typing.Protocol):
    on_atomic_started: IAsyncSignal[SessionScopeStartedEvent]
    on_atomic_ended: IAsyncSignal[SessionScopeEndedEvent]

    def atomic(self) -> typing.AsyncContextManager["ISession"]:
        ...


class ISessionPool(typing.Protocol):
    on_session_started: IAsyncSignal[SessionScopeStartedEvent]
    on_session_ended: IAsyncSignal[SessionScopeEndedEvent]

    def session(self) -> typing.AsyncContextManager[ISession]:
        raise NotImplementedError


# Infrastructure layer interfaces:

Query: typing.TypeAlias = typing.Union[str, bytes]
Params: typing.TypeAlias = typing.Union[typing.Sequence[typing.Any], typing.Mapping[str, typing.Any]]
TupleRow = tuple[typing.Any, ...]
Row = TypeVar("Row", default=TupleRow)


@typing.runtime_checkable
class IAsyncCursor(typing.Protocol[Row]):
    async def execute(
        self,
        query: Query,
        params: Params | None = None,
        *,
        prepare: bool | None = None,
        binary: bool | None = None,
    ) -> "IAsyncCursor[Row]": ...

    async def fetchone(self) -> Row | None:
        ...

    async def fetchmany(self, size: int = 0) -> list[Row]:
        ...

    async def fetchall(self) -> list[Row]:
        ...

    async def close(self) -> None:
        ...

    async def __aenter__(self) -> "IAsyncCursor[Row]":
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        ...


@typing.runtime_checkable
class IAsyncTransaction(typing.Protocol[Row]):
    connection: "IAsyncConnection[Row]"

    async def __aenter__(self) -> "IAsyncTransaction[Row]":
        ...

    async def __aexit__(
        self,
        exc_type: typing.Optional[type[BaseException]],
        exc_val: typing.Optional[BaseException],
        exc_tb: typing.Any,
    ) -> None:
        ...


@typing.runtime_checkable
class IAsyncConnection(typing.Protocol[Row]):
    def cursor(self, *args: typing.Any, **kwargs: typing.Any) -> IAsyncCursor[Row]:
        ...

    def transaction(
        self,
        savepoint_name: str | None = None,
        force_rollback: bool = False
    ) -> typing.AsyncContextManager["IAsyncTransaction[Row]"]:
        ...

    async def close(self) -> None:
        ...

    async def execute(
        self,
        query: Query,
        params: Params | None = None,
        *,
        prepare: bool | None = None,
        binary: bool = False,
    ) -> IAsyncCursor[Row]: ...

    async def __aenter__(self) -> "IAsyncConnection[Row]":
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        ...


class IAsyncConnectionPool(typing.Protocol[Row]):
    def connection(self, timeout: float | None = None) -> typing.AsyncContextManager["IAsyncConnection[Row]"]:
        ...


T = TypeVar("T")


@dataclass(frozen=True)
class IdentityKey(typing.Generic[T]):
    entity_type: type[T]
    entity_id: Hashable


class IIdentityMap(metaclass=ABCMeta):
    @abstractmethod
    def get(self, key: IdentityKey[T]) -> T:
        raise NotImplementedError

    @abstractmethod
    def has(self, key: IdentityKey[typing.Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def add(self, key: IdentityKey[T], value: T | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove(self, key: IdentityKey[typing.Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError


@typing.runtime_checkable
class IPgSession(ISession, typing.Protocol):
    identity_map: IIdentityMap
    connection: IAsyncConnection[tuple[typing.Any, ...]]
    on_query_started: IAsyncSignal[QueryStartedEvent]
    on_query_ended: IAsyncSignal[QueryEndedEvent]


@typing.runtime_checkable
class IRestSession(ISession, typing.Protocol):
    identity_map: IIdentityMap
    request: ClientSession
    on_request_started: IAsyncSignal[RequestStartedEvent]
    on_request_ended: IAsyncSignal[RequestEndedEvent]
