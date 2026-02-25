from dataclasses import dataclass
from unittest import IsolatedAsyncioTestCase, mock

from ascetic_ddd.mediator.interfaces import IRequest
from ascetic_ddd.mediator.mediator import Mediator


class Session:
    pass


@dataclass(frozen=True)
class SampleEvent:
    payload: int


@dataclass(frozen=True)
class AnotherEvent:
    payload: str


@dataclass(frozen=True)
class SampleCommand(IRequest[int]):
    payload: int


@dataclass(frozen=True)
class AnotherCommand(IRequest[str]):
    payload: str


class PublishTestCase(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mediator = Mediator[Session]()
        self.session = Session()

    async def test_publish_calls_subscriber(self):
        handler = mock.AsyncMock()
        await self.mediator.subscribe(SampleEvent, handler)
        event = SampleEvent(2)
        await self.mediator.publish(self.session, event)
        handler.assert_called_once_with(self.session, event)

    async def test_publish_calls_multiple_subscribers(self):
        handler1 = mock.AsyncMock()
        handler2 = mock.AsyncMock()
        await self.mediator.subscribe(SampleEvent, handler1)
        await self.mediator.subscribe(SampleEvent, handler2)
        event = SampleEvent(3)
        await self.mediator.publish(self.session, event)
        handler1.assert_called_once_with(self.session, event)
        handler2.assert_called_once_with(self.session, event)

    async def test_publish_does_not_call_subscriber_of_other_event_type(self):
        handler = mock.AsyncMock()
        await self.mediator.subscribe(AnotherEvent, handler)
        await self.mediator.publish(self.session, SampleEvent(1))
        handler.assert_not_called()

    async def test_publish_with_no_subscribers(self):
        await self.mediator.publish(self.session, SampleEvent(1))


class UnsubscribeTestCase(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mediator = Mediator[Session]()
        self.session = Session()

    async def test_unsubscribe_removes_handler(self):
        handler = mock.AsyncMock()
        handler2 = mock.AsyncMock()
        await self.mediator.subscribe(SampleEvent, handler)
        await self.mediator.subscribe(SampleEvent, handler2)
        await self.mediator.unsubscribe(SampleEvent, handler)
        event = SampleEvent(2)
        await self.mediator.publish(self.session, event)
        handler.assert_not_called()
        handler2.assert_called_once_with(self.session, event)

    async def test_unsubscribe_nonexistent_handler_is_noop(self):
        handler = mock.AsyncMock()
        await self.mediator.unsubscribe(SampleEvent, handler)

    async def test_dispose_unsubscribes(self):
        handler = mock.AsyncMock()
        handler2 = mock.AsyncMock()
        disposable = await self.mediator.subscribe(SampleEvent, handler)
        await self.mediator.subscribe(SampleEvent, handler2)
        await disposable.dispose()
        event = SampleEvent(2)
        await self.mediator.publish(self.session, event)
        handler.assert_not_called()
        handler2.assert_called_once_with(self.session, event)


class SendTestCase(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mediator = Mediator[Session]()
        self.session = Session()

    async def test_send_calls_handler_and_returns_result(self):
        handler = mock.AsyncMock(return_value=5)
        await self.mediator.register(SampleCommand, handler)
        command = SampleCommand(2)
        result = await self.mediator.send(self.session, command)
        handler.assert_called_once_with(self.session, command)
        self.assertEqual(result, 5)

    async def test_send_raises_when_no_handler(self):
        with self.assertRaises(RuntimeError):
            await self.mediator.send(self.session, SampleCommand(1))

    async def test_send_dispatches_by_request_type(self):
        handler1 = mock.AsyncMock(return_value=10)
        handler2 = mock.AsyncMock(return_value="hello")
        await self.mediator.register(SampleCommand, handler1)
        await self.mediator.register(AnotherCommand, handler2)
        result1 = await self.mediator.send(self.session, SampleCommand(1))
        result2 = await self.mediator.send(self.session, AnotherCommand("x"))
        self.assertEqual(result1, 10)
        self.assertEqual(result2, "hello")


class UnregisterTestCase(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mediator = Mediator[Session]()
        self.session = Session()

    async def test_unregister_removes_handler(self):
        handler = mock.AsyncMock()
        await self.mediator.register(SampleCommand, handler)
        await self.mediator.unregister(SampleCommand)
        with self.assertRaises(RuntimeError):
            await self.mediator.send(self.session, SampleCommand(2))
        handler.assert_not_called()

    async def test_unregister_nonexistent_raises(self):
        with self.assertRaises(KeyError):
            await self.mediator.unregister(SampleCommand)

    async def test_dispose_unregisters(self):
        handler = mock.AsyncMock()
        disposable = await self.mediator.register(SampleCommand, handler)
        await disposable.dispose()
        with self.assertRaises(RuntimeError):
            await self.mediator.send(self.session, SampleCommand(2))
        handler.assert_not_called()


class PipelineTestCase(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mediator = Mediator[Session]()
        self.session = Session()

    async def test_typed_pipeline_wraps_handler(self):
        call_log = []

        async def handler(session, request):
            call_log.append("handler")
            return request.payload * 2

        async def pipeline(session, request, next_):
            call_log.append("before")
            result = await next_(session, request)
            call_log.append("after")
            return result

        await self.mediator.register(SampleCommand, handler)
        await self.mediator.add_pipeline(SampleCommand, pipeline)
        result = await self.mediator.send(self.session, SampleCommand(3))
        self.assertEqual(result, 6)
        self.assertEqual(call_log, ["before", "handler", "after"])

    async def test_broadcast_pipeline_wraps_all_request_types(self):
        call_log = []

        async def handler1(session, request):
            call_log.append("handler1")
            return request.payload

        async def handler2(session, request):
            call_log.append("handler2")
            return request.payload

        async def pipeline(session, request, next_):
            call_log.append("broadcast")
            return await next_(session, request)

        await self.mediator.register(SampleCommand, handler1)
        await self.mediator.register(AnotherCommand, handler2)
        await self.mediator.add_pipeline(None, pipeline)

        await self.mediator.send(self.session, SampleCommand(1))
        await self.mediator.send(self.session, AnotherCommand("x"))
        self.assertEqual(call_log, [
            "broadcast", "handler1",
            "broadcast", "handler2",
        ])

    async def test_multiple_pipelines_execute_in_order(self):
        call_log = []

        async def handler(session, request):
            call_log.append("handler")
            return 0

        async def pipeline_a(session, request, next_):
            call_log.append("A-before")
            result = await next_(session, request)
            call_log.append("A-after")
            return result

        async def pipeline_b(session, request, next_):
            call_log.append("B-before")
            result = await next_(session, request)
            call_log.append("B-after")
            return result

        await self.mediator.register(SampleCommand, handler)
        await self.mediator.add_pipeline(SampleCommand, pipeline_a)
        await self.mediator.add_pipeline(SampleCommand, pipeline_b)
        await self.mediator.send(self.session, SampleCommand(1))
        # First added pipeline is outermost
        self.assertEqual(call_log, [
            "A-before", "B-before", "handler", "B-after", "A-after",
        ])

    async def test_broadcast_pipeline_runs_before_typed_pipeline(self):
        call_log = []

        async def handler(session, request):
            call_log.append("handler")
            return 0

        async def broadcast(session, request, next_):
            call_log.append("broadcast")
            return await next_(session, request)

        async def typed(session, request, next_):
            call_log.append("typed")
            return await next_(session, request)

        await self.mediator.register(SampleCommand, handler)
        await self.mediator.add_pipeline(None, broadcast)
        await self.mediator.add_pipeline(SampleCommand, typed)
        await self.mediator.send(self.session, SampleCommand(1))
        self.assertEqual(call_log, ["broadcast", "typed", "handler"])

    async def test_pipeline_can_modify_result(self):
        async def handler(session, request):
            return request.payload

        async def pipeline(session, request, next_):
            result = await next_(session, request)
            return result + 100

        await self.mediator.register(SampleCommand, handler)
        await self.mediator.add_pipeline(SampleCommand, pipeline)
        result = await self.mediator.send(self.session, SampleCommand(5))
        self.assertEqual(result, 105)

    async def test_pipeline_not_applied_to_other_request_type(self):
        call_log = []

        async def handler(session, request):
            return request.payload

        async def pipeline(session, request, next_):
            call_log.append("pipeline")
            return await next_(session, request)

        await self.mediator.register(SampleCommand, handler)
        await self.mediator.register(AnotherCommand, handler)
        await self.mediator.add_pipeline(SampleCommand, pipeline)
        await self.mediator.send(self.session, AnotherCommand("x"))
        self.assertEqual(call_log, [])

    async def test_send_without_handler_raises(self):
        call_log = []

        async def pipeline(session, request, next_):
            call_log.append("pipeline")
            return await next_(session, request)

        await self.mediator.add_pipeline(SampleCommand, pipeline)
        with self.assertRaises(RuntimeError):
            await self.mediator.send(self.session, SampleCommand(1))
        self.assertEqual(call_log, [])
