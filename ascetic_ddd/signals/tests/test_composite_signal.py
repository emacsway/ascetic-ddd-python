import asyncio
from dataclasses import dataclass
from unittest import IsolatedAsyncioTestCase, mock

from ascetic_ddd.signals.signal import SyncSignal, AsyncSignal
from ascetic_ddd.signals.composite_signal import SyncCompositeSignal, AsyncCompositeSignal


@dataclass(frozen=True)
class SampleEvent:
    payload: int


# noinspection PyMethodMayBeStatic
class SyncCompositeSignalTestCase(IsolatedAsyncioTestCase):

    def setUp(self):
        self.signal1 = SyncSignal()
        self.signal2 = SyncSignal()
        self.composite = SyncCompositeSignal(self.signal1, self.signal2)

    def test_attach_propagates_to_all_delegates(self):
        observer = mock.Mock()
        self.composite.attach(observer, observer_id="obs")
        event = SampleEvent(1)
        self.signal1.notify(event)
        self.signal2.notify(event)
        self.assertEqual(observer.call_count, 2)

    def test_detach_propagates_to_all_delegates(self):
        observer = mock.Mock()
        self.composite.attach(observer, observer_id="obs")
        self.composite.detach(observer, observer_id="obs")
        event = SampleEvent(1)
        self.signal1.notify(event)
        self.signal2.notify(event)
        observer.assert_not_called()

    def test_notify_propagates_to_all_delegates(self):
        observer = mock.Mock()
        self.composite.attach(observer, observer_id="obs")
        event = SampleEvent(1)
        self.composite.notify(event)
        self.assertEqual(observer.call_count, 2)
        observer.assert_called_with(event)

    async def test_disposable_detaches_from_all_delegates(self):
        observer = mock.Mock()
        disposable = self.composite.attach(observer, observer_id="obs")
        await disposable.dispose()
        event = SampleEvent(1)
        self.signal1.notify(event)
        self.signal2.notify(event)
        observer.assert_not_called()

    def test_notify_no_delegates(self):
        composite = SyncCompositeSignal()
        composite.notify(SampleEvent(1))

    def test_notify_single_delegate(self):
        signal = SyncSignal()
        composite = SyncCompositeSignal(signal)
        observer = mock.Mock()
        composite.attach(observer, observer_id="obs")
        event = SampleEvent(1)
        composite.notify(event)
        observer.assert_called_once_with(event)


# noinspection PyMethodMayBeStatic
class AsyncCompositeSignalTestCase(IsolatedAsyncioTestCase):

    def setUp(self):
        self.signal1 = AsyncSignal()
        self.signal2 = AsyncSignal()
        self.composite = AsyncCompositeSignal(self.signal1, self.signal2)

    async def test_attach_propagates_to_all_delegates(self):
        observer = mock.AsyncMock()
        self.composite.attach(observer, observer_id="obs")
        event = SampleEvent(1)
        await self.signal1.notify(event)
        await self.signal2.notify(event)
        self.assertEqual(observer.call_count, 2)

    async def test_detach_propagates_to_all_delegates(self):
        observer = mock.AsyncMock()
        self.composite.attach(observer, observer_id="obs")
        self.composite.detach(observer, observer_id="obs")
        event = SampleEvent(1)
        await self.signal1.notify(event)
        await self.signal2.notify(event)
        observer.assert_not_called()

    async def test_notify_propagates_to_all_delegates(self):
        observer = mock.AsyncMock()
        self.composite.attach(observer, observer_id="obs")
        event = SampleEvent(1)
        await self.composite.notify(event)
        self.assertEqual(observer.call_count, 2)
        observer.assert_called_with(event)

    async def test_disposable_detaches_from_all_delegates(self):
        observer = mock.AsyncMock()
        disposable = self.composite.attach(observer, observer_id="obs")
        await disposable.dispose()
        event = SampleEvent(1)
        await self.signal1.notify(event)
        await self.signal2.notify(event)
        observer.assert_not_called()

    async def test_notify_no_delegates(self):
        composite = AsyncCompositeSignal()
        await composite.notify(SampleEvent(1))

    async def test_notify_single_delegate(self):
        signal = AsyncSignal()
        composite = AsyncCompositeSignal(signal)
        observer = mock.AsyncMock()
        composite.attach(observer, observer_id="obs")
        event = SampleEvent(1)
        await composite.notify(event)
        observer.assert_called_once_with(event)

    async def test_notify_awaits_delegates_sequentially(self):
        call_order = []

        async def observer(event):
            call_order.append(event.payload)

        signal1 = AsyncSignal()
        signal2 = AsyncSignal()
        composite = AsyncCompositeSignal(signal1, signal2)

        composite.attach(observer, observer_id="obs")
        await composite.notify(SampleEvent(1))
        # Observer called once per delegate, in order
        self.assertEqual(call_order, [1, 1])
