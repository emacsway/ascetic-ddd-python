"""Unit tests for Deferred pattern implementation."""
import unittest

from ascetic_ddd.deferred.deferred import Deferred, noop


class TestNoop(unittest.TestCase):
    """Test noop function."""

    def test_noop_returns_none(self):
        """Test that noop returns None for any input."""
        self.assertIsNone(noop(42))
        self.assertIsNone(noop("test"))
        self.assertIsNone(noop(None))


class TestDeferredBasics(unittest.TestCase):
    """Test basic Deferred functionality."""

    def test_resolve_triggers_success_handler(self):
        """Test that resolving triggers the success handler."""
        deferred = Deferred[int]()
        result = []

        def on_success(value: int) -> int:
            result.append(value)
            return value

        deferred.then(on_success, noop)
        deferred.resolve(42)

        self.assertEqual([42], result)

    def test_reject_triggers_error_handler(self):
        """Test that rejecting triggers the error handler."""
        deferred = Deferred[int]()
        result = []

        def on_error(err: Exception) -> None:
            result.append(err)
            return None

        test_error = ValueError("test error")
        deferred.then(noop, on_error)
        deferred.reject(test_error)

        self.assertEqual([test_error], result)

    def test_resolve_before_then(self):
        """Test resolving before registering handlers."""
        deferred = Deferred[int]()
        result = []

        deferred.resolve(42)

        def on_success(value: int) -> int:
            result.append(value)
            return value

        deferred.then(on_success, noop)

        self.assertEqual([42], result)

    def test_reject_before_then(self):
        """Test rejecting before registering handlers."""
        deferred = Deferred[int]()
        result = []

        test_error = ValueError("test error")
        deferred.reject(test_error)

        def on_error(err: Exception) -> None:
            result.append(err)
            return None

        deferred.then(noop, on_error)

        self.assertEqual([test_error], result)


class TestDeferredChaining(unittest.TestCase):
    """Test Deferred chaining with then()."""

    def test_chain_success_handlers(self):
        """Test chaining multiple success handlers."""
        deferred = Deferred[int]()
        results = []

        def handler1(value: int) -> str:
            results.append("handler1: %s" % value)
            return "transformed_%s" % value

        def handler2(value: str) -> str:
            results.append("handler2: %s" % value)
            return value

        deferred.then(handler1, noop).then(handler2, noop)
        deferred.resolve(42)

        self.assertEqual(
            ["handler1: 42", "handler2: transformed_42"], results
        )

    def test_chain_with_error_propagation(self):
        """Test error propagation through chain."""
        deferred = Deferred[int]()
        results = []

        test_error = ValueError("test error")

        def handler1(value: int) -> str:
            results.append("handler1: %s" % value)
            raise test_error

        def handler2(value: str) -> str:
            results.append("handler2: should not be called")
            return value

        def error_handler(err: Exception) -> None:
            results.append("error: %s" % err)
            return None

        deferred.then(handler1, noop).then(handler2, error_handler)
        deferred.resolve(42)

        self.assertEqual(
            ["handler1: 42", "error: %s" % test_error], results
        )

    def test_multiple_handlers_on_same_deferred(self):
        """Test registering multiple handlers on the same deferred."""
        deferred = Deferred[int]()
        results = []

        def handler1(value: int) -> int:
            results.append("handler1: %s" % value)
            return value

        def handler2(value: int) -> int:
            results.append("handler2: %s" % value)
            return value

        deferred.then(handler1, noop)
        deferred.then(handler2, noop)
        deferred.resolve(42)

        # Both handlers should be called
        self.assertIn("handler1: 42", results)
        self.assertIn("handler2: 42", results)
        self.assertEqual(2, len(results))


class TestErrorCollection(unittest.TestCase):
    """Test error collection with occurred_err()."""

    def test_occurred_err_empty_when_no_errors(self):
        """Test that occurred_err returns empty list when no errors."""
        deferred = Deferred[int]()

        def on_success(value: int) -> int:
            return value

        deferred.then(on_success, noop)
        deferred.resolve(42)

        errors = deferred.occurred_err()
        self.assertEqual([], errors)

    def test_occurred_err_collects_handler_errors(self):
        """Test that occurred_err collects errors from handlers."""
        deferred = Deferred[int]()
        error1 = ValueError("error 1")

        def failing_handler(_: int) -> int:
            raise error1

        deferred.then(failing_handler, noop)
        deferred.resolve(42)

        errors = deferred.occurred_err()
        self.assertEqual([error1], errors)

    def test_occurred_err_collects_nested_errors(self):
        """Test that occurred_err collects errors from entire chain."""
        deferred = Deferred[int]()
        error1 = ValueError("error 1")
        error2 = RuntimeError("error 2")

        def failing_handler1(_: int) -> int:
            raise error1

        def failing_error_handler(err: Exception) -> None:
            raise error2

        deferred.then(failing_handler1, noop).then(noop, failing_error_handler)
        deferred.resolve(42)

        errors = deferred.occurred_err()
        self.assertEqual([error1, error2], errors)

    def test_occurred_err_with_multiple_branches(self):
        """Test error collection from multiple handler branches."""
        deferred = Deferred[int]()
        error1 = ValueError("error 1")
        error2 = RuntimeError("error 2")

        def failing_handler1(_: int) -> int:
            raise error1

        def failing_handler2(_: int) -> int:
            raise error2

        deferred.then(failing_handler1, noop)
        deferred.then(failing_handler2, noop)
        deferred.resolve(42)

        errors = deferred.occurred_err()
        # Both errors should be collected
        self.assertIn(error1, errors)
        self.assertIn(error2, errors)
        self.assertEqual(2, len(errors))


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and special scenarios."""

    def test_resolve_with_none(self):
        """Test resolving with None value."""
        deferred = Deferred[None]()
        result = []

        def on_success(value: None) -> None:
            result.append(value)
            return None

        deferred.then(on_success, noop)
        deferred.resolve(None)

        self.assertEqual([None], result)

    def test_error_handler_recovers_with_value(self):
        """Test error handler that returns a value (recovery)."""
        deferred = Deferred[int]()
        results = []

        test_error = ValueError("test error")

        def on_error(err: Exception) -> str:
            results.append("error handled")
            return "recovered"

        def next_handler(value: str) -> str:
            results.append("next handler: %s" % value)
            return value

        deferred.then(noop, on_error).then(next_handler, noop)
        deferred.reject(test_error)

        # Error handler recovers, so next handler should be called
        # with the recovered value
        self.assertEqual(["error handled", "next handler: recovered"], results)

    def test_error_handler_returning_none_recovers(self):
        """Test error handler that returns None resolves next deferred with None."""
        deferred = Deferred[int]()
        results = []

        test_error = ValueError("test error")

        def on_error(err: Exception) -> None:
            results.append("error handled")
            return None

        def next_handler(value: None) -> None:
            results.append("next handler called")
            return None

        deferred.then(noop, on_error).then(next_handler, noop)
        deferred.reject(test_error)

        # Error handler returns None (recovery), so next handler should be called
        self.assertEqual(["error handled", "next handler called"], results)

    def test_multiple_resolves_triggers_handlers_multiple_times(self):
        """Test that multiple resolves trigger handlers each time."""
        deferred = Deferred[int]()
        results = []

        def on_success(value: int) -> int:
            results.append(value)
            return value

        deferred.then(on_success, noop)
        deferred.resolve(42)
        deferred.resolve(100)  # Triggers handlers again

        # Each resolve triggers all handlers
        self.assertEqual([42, 100], results)


class TestComplexScenarios(unittest.TestCase):
    """Test complex real-world scenarios."""

    def test_cleanup_chain(self):
        """Test a cleanup chain with multiple operations."""
        deferred = Deferred[str]()
        cleanup_log = []

        def cleanup1(resource: str) -> str:
            cleanup_log.append("cleanup1: %s" % resource)
            return resource

        def cleanup2(value: str) -> str:
            cleanup_log.append("cleanup2: %s" % value)
            return value

        def cleanup3(value: str) -> str:
            cleanup_log.append("cleanup3: %s" % value)
            return value

        deferred.then(cleanup1, noop).then(cleanup2, noop).then(cleanup3, noop)
        deferred.resolve("database_connection")

        self.assertEqual(
            [
                "cleanup1: database_connection",
                "cleanup2: database_connection",
                "cleanup3: database_connection",
            ],
            cleanup_log,
        )

    def test_value_transformation_chain(self):
        """Test chain where each step transforms the value."""
        deferred = Deferred[int]()
        results = []

        def double(value: int) -> int:
            results.append("double: %s" % value)
            return value * 2

        def add_ten(value: int) -> int:
            results.append("add_ten: %s" % value)
            return value + 10

        def to_string(value: int) -> str:
            results.append("to_string: %s" % value)
            return "result_%s" % value

        deferred.then(double, noop).then(add_ten, noop).then(to_string, noop)
        deferred.resolve(5)

        self.assertEqual(
            ["double: 5", "add_ten: 10", "to_string: 20"], results
        )

    def test_partial_failure_chain(self):
        """Test chain where some operations fail and some succeed."""
        deferred = Deferred[int]()
        results = []

        error = ValueError("step 2 failed")

        def step1(value: int) -> int:
            results.append("step1: %s" % value)
            return value

        def step2(value: int) -> int:
            results.append("step2: failing")
            raise error

        def step3(value: int) -> int:
            results.append("step3: should not execute")
            return value

        def handle_error(err: Exception) -> None:
            results.append("error handler: %s" % err)
            return None

        (
            deferred.then(step1, noop)
            .then(step2, noop)
            .then(step3, handle_error)
        )

        deferred.resolve(42)

        self.assertEqual(
            ["step1: 42", "step2: failing", "error handler: %s" % error],
            results,
        )


class TestDeferredAll(unittest.TestCase):
    """Test Deferred.all() static method."""

    def test_all_resolves_when_all_resolved(self):
        """Test that all() resolves with list of values when all deferreds resolve."""
        d1 = Deferred[int]()
        d2 = Deferred[int]()
        d3 = Deferred[int]()

        combined = Deferred.all([d1, d2, d3])
        result = []

        def on_success(values: list) -> None:
            result.extend(values)
            return None

        combined.then(on_success, noop)

        d1.resolve(1)
        d2.resolve(2)
        d3.resolve(3)

        self.assertEqual([1, 2, 3], result)

    def test_all_rejects_on_first_error(self):
        """Test that all() rejects with the first error when any deferred rejects."""
        d1 = Deferred[int]()
        d2 = Deferred[int]()
        d3 = Deferred[int]()

        combined = Deferred.all([d1, d2, d3])
        errors = []

        def on_error(err: Exception) -> None:
            errors.append(err)
            return None

        combined.then(noop, on_error)

        test_error = ValueError("fail")
        d1.resolve(1)
        d2.reject(test_error)

        self.assertEqual([test_error], errors)

    def test_all_empty_list(self):
        """Test that all() with empty list resolves immediately with []."""
        combined = Deferred.all([])
        result = []

        def on_success(values: list) -> None:
            result.append(values)
            return None

        combined.then(on_success, noop)

        self.assertEqual([[]], result)

    def test_all_preserves_order(self):
        """Test that all() preserves order regardless of resolution order."""
        d1 = Deferred[str]()
        d2 = Deferred[str]()
        d3 = Deferred[str]()

        combined = Deferred.all([d1, d2, d3])
        result = []

        def on_success(values: list) -> None:
            result.extend(values)
            return None

        combined.then(on_success, noop)

        # Resolve in reverse order
        d3.resolve("third")
        d1.resolve("first")
        d2.resolve("second")

        self.assertEqual(["first", "second", "third"], result)

    def test_all_single_deferred(self):
        """Test that all() works with a single deferred."""
        d = Deferred[int]()

        combined = Deferred.all([d])
        result = []

        def on_success(values: list) -> None:
            result.extend(values)
            return None

        combined.then(on_success, noop)

        d.resolve(42)

        self.assertEqual([42], result)


if __name__ == "__main__":
    unittest.main()
