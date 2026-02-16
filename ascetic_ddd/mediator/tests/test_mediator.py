from dataclasses import dataclass
from unittest import IsolatedAsyncioTestCase, mock

from ascetic_ddd.mediator.mediator import Mediator


class IEvent:
    pass


class ICommand:
    pass


class Session:
    pass


@dataclass(frozen=True)
class SampleDomainEvent(IEvent):
    payload: int


@dataclass(frozen=True)
class SampleCommand(ICommand):
    payload: int


class MediatorTestCase(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mediator = Mediator[Session]()
        self.session = Session()

    async def test_publish(self):
        handler = mock.AsyncMock()
        await self.mediator.subscribe(SampleDomainEvent, handler)
        event = SampleDomainEvent(2)
        await self.mediator.publish(self.session, event)
        handler.assert_called_once_with(self.session, event)

    async def test_unsubscribe(self):
        handler = mock.AsyncMock()
        handler2 = mock.AsyncMock()
        await self.mediator.subscribe(SampleDomainEvent, handler)
        await self.mediator.subscribe(SampleDomainEvent, handler2)
        await self.mediator.unsubscribe(SampleDomainEvent, handler)
        event = SampleDomainEvent(2)
        await self.mediator.publish(self.session, event)
        handler.assert_not_called()
        handler2.assert_called_once_with(self.session, event)

    async def test_disposable_event(self):
        handler = mock.AsyncMock()
        handler2 = mock.AsyncMock()
        disposable = await self.mediator.subscribe(SampleDomainEvent, handler)
        await self.mediator.subscribe(SampleDomainEvent, handler2)
        await disposable.dispose()
        event = SampleDomainEvent(2)
        await self.mediator.publish(self.session, event)
        handler.assert_not_called()
        handler2.assert_called_once_with(self.session, event)

    async def test_send(self):
        handler = mock.AsyncMock(return_value=5)
        await self.mediator.register(SampleCommand, handler)
        command = SampleCommand(2)
        result = await self.mediator.send(self.session, command)
        handler.assert_called_once_with(self.session, command)
        self.assertEqual(result, 5)

    async def test_unregister(self):
        handler = mock.AsyncMock()
        await self.mediator.register(SampleCommand, handler)
        await self.mediator.unregister(SampleCommand)
        command = SampleCommand(2)
        await self.mediator.send(self.session, command)
        handler.assert_not_called()

    async def test_disposable_command(self):
        handler = mock.AsyncMock()
        disposable = await self.mediator.register(SampleCommand, handler)
        await disposable.dispose()
        command = SampleCommand(2)
        await self.mediator.send(self.session, command)
        handler.assert_not_called()
