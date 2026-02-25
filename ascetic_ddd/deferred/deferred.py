"""
Deferred pattern implementation.

Simplified version of:
- https://github.com/emacsway/store/blob/devel/polyfill.js#L199
- https://github.com/emacsway/go-promise

See also:
- https://promisesaplus.com/
- http://promises-aplus.github.io/promises-spec/
"""
import typing
from typing import Any, Callable, Generic, Iterable, TypeVar

from ascetic_ddd.deferred.interfaces import IDeferred

T = TypeVar("T")
R = TypeVar("R")


def noop(_: T) -> None:
    """No-operation callback."""
    return None


class _Handler(Generic[T, R]):
    """Internal handler for deferred callbacks."""

    def __init__(
        self,
        on_success: Callable[[T], R],
        on_error: Callable[[Exception], R],
        next_deferred: "Deferred[R]",
    ):
        self.on_success = on_success
        self.on_error = on_error
        self.next = next_deferred


class Deferred(IDeferred[T]):
    """
    Implementation of the Deferred pattern.

    Provides a way to handle asynchronous operations with callbacks
    for both success and error cases, similar to JavaScript Promises.
    """

    def __init__(self) -> None:
        self._value: T | None = None
        self._err: Exception | None = None
        self._occurred_errors: list[Exception] = []
        self._is_resolved = False
        self._is_rejected = False
        self._handlers: list[_Handler[T, Any]] = []

    def resolve(self, value: T) -> None:
        """
        Resolve the deferred with a value.

        Triggers all registered success handlers.

        Args:
            value: The value to resolve with
        """
        self._value = value
        self._is_resolved = True
        for handler in self._handlers:
            self._resolve_handler(handler)

    def reject(self, err: Exception) -> None:
        """
        Reject the deferred with an error.

        Triggers all registered error handlers.

        Args:
            err: The error to reject with
        """
        self._err = err
        self._is_rejected = True
        for handler in self._handlers:
            self._reject_handler(handler)

    def then(
        self,
        on_success: Callable[[T], R],
        on_error: Callable[[Exception], R],
    ) -> "Deferred[R]":
        """
        Register callbacks for success and error cases.

        Per Promises/A+ 2.2.7:
        - If on_success returns a value, next deferred is resolved with it.
        - If on_success raises an exception, next deferred is rejected with it.
        - If on_error returns a value, next deferred is resolved with it (recovery).
        - If on_error raises an exception, next deferred is rejected with it.

        Returns:
            New Deferred for chaining
        """
        next_deferred = Deferred[R]()
        handler = _Handler(on_success, on_error, next_deferred)
        self._handlers.append(handler)

        if self._is_resolved:
            self._resolve_handler(handler)
        elif self._is_rejected:
            self._reject_handler(handler)

        return next_deferred

    def _resolve_handler(self, handler: _Handler[T, Any]) -> None:
        """
        Execute success handler (Promises/A+ 2.2.7.1-2).

        If handler returns a value, resolve the next deferred with it.
        If handler raises an exception, reject the next deferred with it.
        """
        try:
            result = handler.on_success(typing.cast(T, self._value))
            handler.next.resolve(result)
        except Exception as e:
            self._occurred_errors.append(e)
            handler.next.reject(e)

    def _reject_handler(self, handler: _Handler[T, Any]) -> None:
        """
        Execute error handler (Promises/A+ 2.2.7.3-4).

        If handler returns a value, resolve the next deferred with it (recovery).
        If handler raises an exception, reject the next deferred with it.
        """
        try:
            result = handler.on_error(typing.cast(Exception, self._err))
            handler.next.resolve(result)
        except Exception as e:
            self._occurred_errors.append(e)
            handler.next.reject(e)

    def occurred_err(self) -> list[Exception]:
        """
        Collect all errors that occurred during execution.

        Recursively collects errors from the entire chain of deferreds.

        Returns:
            List of all exceptions that occurred
        """
        errors = self._occurred_errors.copy()
        for handler in self._handlers:
            nested_errors = handler.next.occurred_err()
            if nested_errors:
                errors.extend(nested_errors)
        return errors

    @staticmethod
    def all(deferreds: Iterable['IDeferred[T]']) -> 'Deferred[list[T]]':
        """
        Return a Deferred that resolves when all input deferreds resolve.

        Similar to Promise.all in ES6:
        - Resolves with a list of values (preserving order) when all resolve.
        - Rejects with the first error when any deferred rejects.

        Args:
            deferreds: Iterable of deferreds to wait for.

        Returns:
            A Deferred that resolves with list[T].
        """
        deferreds_list = list(deferreds)
        result = Deferred[list[T]]()

        if not deferreds_list:
            result.resolve([])
            return result

        count = len(deferreds_list)
        values: list[T | None] = [None] * count
        resolved_count = [0]
        rejected = [False]

        for i, d in enumerate(deferreds_list):
            def on_success(value: T, idx: int = i) -> None:
                if rejected[0]:
                    return None
                values[idx] = value
                resolved_count[0] += 1
                if resolved_count[0] == count:
                    result.resolve(list(values))  # type: ignore[arg-type]
                return None

            def on_error(err: Exception, idx: int = i) -> None:
                if not rejected[0]:
                    rejected[0] = True
                    result.reject(err)
                return None

            d.then(on_success, on_error)

        return result
