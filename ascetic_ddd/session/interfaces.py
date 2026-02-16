import typing

from abc import ABCMeta, abstractmethod
from types import TracebackType

from aiohttp import ClientSession

from ascetic_ddd.observable.interfaces import IObservable

__all__ = (
    "Query",
    "Params",
    "Row",
    "IAsyncConnection",
    "IAsyncConnectionPool",
    "IAsyncCursor",
    "IAsyncTransaction",
    "ISession",
    "ISessionPool",
    "IIdentityMap",
    "IIdentityKey",
    "IModel",
    "IPgSession",
    "IRestSession",
)


# Domain layer interfaces:


class ISession(IObservable, typing.Protocol, metaclass=ABCMeta):
    response_time: float

    @abstractmethod
    async def atomic(self) -> typing.AsyncContextManager["ISession"]:
        raise NotImplementedError


class ISessionPool(IObservable, typing.Protocol, metaclass=ABCMeta):
    response_time: float

    @abstractmethod
    def session(self) -> typing.AsyncContextManager[ISession]:
        raise NotImplementedError


# Infrastructure layer interfaces:

Query: typing.TypeAlias = typing.Union[str, bytes]
Params: typing.TypeAlias = typing.Union[typing.Sequence[typing.Any], typing.Mapping[str, typing.Any]]
Row = typing.TypeVar("Row")


@typing.runtime_checkable
class IAsyncCursor(typing.Protocol):
    async def execute(
        self,
        query: Query,
        params: Params | None = None,
        *,
        prepare: bool | None = None,
        binary: bool | None = None,
    ) -> "IAsyncCursor": ...

    async def fetchone(self) -> Row | None:
        ...

    async def fetchmany(self, size: int = 0) -> list[Row]:
        ...

    async def fetchall(self) -> list[Row]:
        ...

    async def close(self) -> None:
        ...

    async def __aenter__(self) -> "IAsyncCursor":
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        ...


@typing.runtime_checkable
class IAsyncTransaction(typing.Protocol):
    @property
    def connection(self) -> "IAsyncConnection":
        ...

    async def __aenter__(self) -> "IAsyncTransaction":
        ...

    async def __aexit__(
        self,
        exc_type: typing.Optional[type[BaseException]],
        exc_val: typing.Optional[BaseException],
        exc_tb: typing.Any,
    ) -> None:
        ...


@typing.runtime_checkable
class IAsyncConnection(typing.Protocol):
    def cursor(self, *args: typing.Any, **kwargs: typing.Any) -> IAsyncCursor:
        ...

    def transaction(
        self,
        savepoint_name: str | None = None,
        force_rollback: bool = False
    ) -> typing.AsyncContextManager["IAsyncTransaction"]:
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
    ) -> IAsyncCursor: ...

    async def __aenter__(self) -> "IAsyncConnection":
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        ...


class IAsyncConnectionPool(typing.Protocol):
    async def connection(self, timeout: float | None = None) -> typing.AsyncContextManager["IAsyncConnection"]:
        ...


class IHashable(typing.Protocol, metaclass=ABCMeta):

    def __eq__(self, other: "IHashable") -> bool:
        ...

    def __hash__(self) -> int:
        raise NotImplementedError


IIdentityKey: typing.TypeAlias = IHashable
IModel: typing.TypeAlias = typing.Any


class IIdentityMap(metaclass=ABCMeta):
    @abstractmethod
    def get(self, key: IIdentityKey) -> IModel | None:
        raise NotImplementedError

    @abstractmethod
    def has(self, key: IIdentityKey) -> bool:
        raise NotImplementedError

    @abstractmethod
    def add(self, key: IIdentityKey, obj: IModel):
        raise NotImplementedError

    @abstractmethod
    def remove(self, key: IIdentityKey) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError


@typing.runtime_checkable
class IPgSession(ISession, typing.Protocol):
    @property
    @abstractmethod
    def identity_map(self) -> IIdentityMap:
        ...

    @property
    @abstractmethod
    def connection(self) -> IAsyncConnection:
        """For ReadModels (Queries)."""
        ...


@typing.runtime_checkable
class IRestSession(ISession, typing.Protocol):

    @property
    @abstractmethod
    def request(self) -> ClientSession:
        """For ReadModels (Queries)."""
        ...
