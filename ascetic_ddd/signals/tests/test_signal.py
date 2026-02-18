import asyncio
from dataclasses import dataclass
from unittest import IsolatedAsyncioTestCase, mock

from ascetic_ddd.signals.signal import SyncSignal, AsyncSignal


@dataclass(frozen=True)
class SampleEvent:
    payload: int


# noinspection PyMethodMayBeStatic
class SyncSignalTestCase(IsolatedAsyncioTestCase):

    def setUp(self):
        self.signal = SyncSignal()

    def test_attach_and_notify(self):
        observer = mock.Mock()
        self.signal.attach(observer)
        event = SampleEvent(1)
        self.signal.notify(event)
        observer.assert_called_once_with(event)

    def test_notify_multiple_observers(self):
        observer1 = mock.Mock()
        observer2 = mock.Mock()
        self.signal.attach(observer1)
        self.signal.attach(observer2)
        event = SampleEvent(1)
        self.signal.notify(event)
        observer1.assert_called_once_with(event)
        observer2.assert_called_once_with(event)

    def test_notify_preserves_order(self):
        call_order = []
        observer1 = mock.Mock(side_effect=lambda e: call_order.append(1))
        observer2 = mock.Mock(side_effect=lambda e: call_order.append(2))
        self.signal.attach(observer1)
        self.signal.attach(observer2)
        self.signal.notify(SampleEvent(1))
        self.assertEqual(call_order, [1, 2])

    def test_detach(self):
        observer = mock.Mock()
        self.signal.attach(observer)
        self.signal.detach(observer)
        self.signal.notify(SampleEvent(1))
        observer.assert_not_called()

    def test_detach_with_observer_id(self):
        observer = mock.Mock()
        self.signal.attach(observer, observer_id="my_id")
        self.signal.detach(observer, observer_id="my_id")
        self.signal.notify(SampleEvent(1))
        observer.assert_not_called()

    def test_detach_nonexistent_raises(self):
        observer = mock.Mock()
        with self.assertRaises(KeyError):
            self.signal.detach(observer)

    def test_attach_with_observer_id(self):
        observer = mock.Mock()
        self.signal.attach(observer, observer_id="custom")
        event = SampleEvent(1)
        self.signal.notify(event)
        observer.assert_called_once_with(event)

    def test_attach_duplicate_is_idempotent(self):
        observer = mock.Mock()
        self.signal.attach(observer)
        self.signal.attach(observer)
        event = SampleEvent(1)
        self.signal.notify(event)
        observer.assert_called_once_with(event)

    def test_attach_duplicate_observer_id_is_idempotent(self):
        observer1 = mock.Mock()
        observer2 = mock.Mock()
        self.signal.attach(observer1, observer_id="same")
        self.signal.attach(observer2, observer_id="same")
        event = SampleEvent(1)
        self.signal.notify(event)
        # First observer wins
        observer1.assert_called_once_with(event)
        observer2.assert_not_called()

    def test_notify_no_observers(self):
        self.signal.notify(SampleEvent(1))

    async def test_disposable_detaches(self):
        observer = mock.Mock()
        disposable = self.signal.attach(observer)
        await disposable.dispose()
        self.signal.notify(SampleEvent(1))
        observer.assert_not_called()

    def test_make_id_for_function(self):
        def handler(event):
            pass
        result = SyncSignal._make_id(handler)
        self.assertEqual(result, id(handler))

    def test_make_id_for_bound_method(self):

        class Handler:
            def handle(self, event):
                pass

        handler = Handler()
        result = SyncSignal._make_id(handler.handle)
        self.assertEqual(result, (id(handler), id(Handler.handle)))


# noinspection PyMethodMayBeStatic
class AsyncSignalTestCase(IsolatedAsyncioTestCase):

    def setUp(self):
        self.signal = AsyncSignal()

    async def test_attach_and_notify(self):
        observer = mock.AsyncMock()
        self.signal.attach(observer)
        event = SampleEvent(1)
        await self.signal.notify(event)
        observer.assert_called_once_with(event)

    async def test_notify_multiple_observers(self):
        observer1 = mock.AsyncMock()
        observer2 = mock.AsyncMock()
        self.signal.attach(observer1)
        self.signal.attach(observer2)
        event = SampleEvent(1)
        await self.signal.notify(event)
        observer1.assert_called_once_with(event)
        observer2.assert_called_once_with(event)

    async def test_notify_preserves_order(self):
        call_order = []

        async def observer1(event):
            call_order.append(1)

        async def observer2(event):
            call_order.append(2)

        self.signal.attach(observer1)
        self.signal.attach(observer2)
        await self.signal.notify(SampleEvent(1))
        self.assertEqual(call_order, [1, 2])

    async def test_detach(self):
        observer = mock.AsyncMock()
        self.signal.attach(observer)
        self.signal.detach(observer)
        await self.signal.notify(SampleEvent(1))
        observer.assert_not_called()

    async def test_detach_with_observer_id(self):
        observer = mock.AsyncMock()
        self.signal.attach(observer, observer_id="my_id")
        self.signal.detach(observer, observer_id="my_id")
        await self.signal.notify(SampleEvent(1))
        observer.assert_not_called()

    async def test_detach_nonexistent_raises(self):
        observer = mock.AsyncMock()
        with self.assertRaises(KeyError):
            self.signal.detach(observer)

    async def test_attach_duplicate_is_idempotent(self):
        observer = mock.AsyncMock()
        self.signal.attach(observer)
        self.signal.attach(observer)
        event = SampleEvent(1)
        await self.signal.notify(event)
        observer.assert_called_once_with(event)

    async def test_notify_no_observers(self):
        await self.signal.notify(SampleEvent(1))

    async def test_disposable_detaches(self):
        observer = mock.AsyncMock()
        disposable = self.signal.attach(observer)
        await disposable.dispose()
        await self.signal.notify(SampleEvent(1))
        observer.assert_not_called()

    async def test_notify_awaits_observers_sequentially(self):
        call_order = []

        async def observer1(event):
            await asyncio.sleep(0.01)
            call_order.append(1)

        async def observer2(event):
            call_order.append(2)

        self.signal.attach(observer1)
        self.signal.attach(observer2)
        await self.signal.notify(SampleEvent(1))
        # observer1 finishes before observer2 starts (sequential)
        self.assertEqual(call_order, [1, 2])
