"""Deferred pattern interfaces."""
import typing
from abc import ABCMeta, abstractmethod
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


class IDeferred(typing.Generic[T], metaclass=ABCMeta):
    """Interface for deferred operations (similar to Promise)."""

    @abstractmethod
    def resolve(self, value: T) -> None:
        """
        Resolve the deferred with a value.

        Triggers all registered success handlers.

        Args:
            value: The value to resolve with
        """
        ...

    @abstractmethod
    def reject(self, err: Exception) -> None:
        """
        Reject the deferred with an error.

        Triggers all registered error handlers.

        Args:
            err: The error to reject with
        """
        ...

    @abstractmethod
    def then(
        self,
        on_success: Callable[[T], R],
        on_error: Callable[[Exception], R],
    ) -> "IDeferred[R]":
        """
        Register callbacks for success and error cases.

        Per Promises/A+ 2.2.7:
        - If on_success returns a value, next deferred is resolved with it.
        - If on_success raises an exception, next deferred is rejected with it.
        - If on_error returns a value, next deferred is resolved with it (recovery).
        - If on_error raises an exception, next deferred is rejected with it.

        Args:
            on_success: Callback to execute on successful resolution.
            on_error: Callback to execute on rejection.

        Returns:
            New Deferred for chaining
        """
        ...

    @abstractmethod
    def occurred_err(self) -> list[Exception]:
        """
        Collect all errors that occurred during execution.

        Recursively collects errors from the entire chain of deferreds.

        Returns:
            List of all exceptions that occurred
        """
        ...
