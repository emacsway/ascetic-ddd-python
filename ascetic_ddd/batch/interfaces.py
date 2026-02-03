"""Batch query interfaces."""
import typing
from abc import ABCMeta, abstractmethod
from types import TracebackType

from ascetic_ddd.deferred.deferred import Deferred
from ascetic_ddd.session.interfaces import (
    IPgSession, Query, Params, Row,
)


__all__ = (
    "IQueryEvaluator",
    "IMultiQuerier",
    "IDeferredCursor",
    "IDeferredConnection",
    "IDeferredPgSession",
)


class IQueryEvaluator(metaclass=ABCMeta):
    """Interface for query evaluation."""

    @abstractmethod
    async def evaluate(self, session: IPgSession) -> None:
        """Evaluate collected queries against the database session."""
        raise NotImplementedError


class IMultiQuerier(IQueryEvaluator, metaclass=ABCMeta):
    """Interface for multi-query batch operations."""

    @abstractmethod
    def execute(
        self,
        query: Query,
        params: Params | None = None,
        *,
        prepare: bool | None = None,
        binary: bool | None = None,
    ) -> Deferred[Row]:
        """
        Add a query to the batch.

        Args:
            query: SQL query string with positional placeholders %s
            params: Sequence of parameter values

        Returns:
            Deferred[Row] that will be resolved when batch is evaluated
        """
        raise NotImplementedError


@typing.runtime_checkable
class IDeferredCursor(typing.Protocol):
    """
    Cursor interface that returns Deferred results.

    Used for batch query collection where results are resolved
    after batch evaluation.
    """

    async def execute(
        self,
        query: Query,
        params: Params | None = None,
        *,
        prepare: bool | None = None,
        binary: bool | None = None,
    ) -> "IDeferredCursor":
        ...

    async def fetchone(self) -> Deferred[Row | None]:
        ...

    async def fetchmany(self, size: int = 0) -> Deferred[list[Row]]:
        ...

    async def fetchall(self) -> Deferred[list[Row]]:
        ...

    async def close(self) -> None:
        ...

    async def __aenter__(self) -> "IDeferredCursor":
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        ...


@typing.runtime_checkable
class IDeferredConnection(typing.Protocol):
    """
    Connection interface that provides deferred cursors.

    Used for batch query collection.
    """

    def cursor(self, *args: typing.Any, **kwargs: typing.Any) -> IDeferredCursor:
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
    ) -> IDeferredCursor:
        ...

    async def __aenter__(self) -> "IDeferredConnection":
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        ...


@typing.runtime_checkable
class IDeferredPgSession(typing.Protocol):
    """
    Session interface for batch query collection.

    Unlike IPgSession which executes queries immediately,
    IDeferredPgSession collects queries and returns Deferred
    results that are resolved after batch evaluation.
    """

    @property
    def connection(self) -> IDeferredConnection:
        ...

    async def evaluate(self, session: IPgSession) -> None:
        """Execute all collected queries against the real session."""
        ...