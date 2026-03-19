import typing

from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.option import Option
from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.signals.signal import AsyncSignal
from ascetic_ddd.faker.domain.distributors.m2o.events import ValueAppendedEvent
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.faker.domain.sequencers.interfaces import ISequencer
from ascetic_ddd.faker.domain.sequencers.sequencer import Sequencer
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification

__all__ = ('SequenceDistributor',)

T = typing.TypeVar("T")


class SequenceDistributor(IM2ODistributor[T], typing.Generic[T]):
    _on_appended: IAsyncSignal[ValueAppendedEvent[T]]

    def __init__(self, sequencer: ISequencer | None = None):
        self._sequencer = sequencer or Sequencer()
        self._on_appended = AsyncSignal[ValueAppendedEvent[T]]()

    @property
    def on_appended(self) -> IAsyncSignal[ValueAppendedEvent[T]]:
        return self._on_appended

    async def next(
            self,
            session: ISession,
            specification: ISpecification[T],
    ) -> Option[T]:
        position = await self._sequencer.next(session, specification)
        raise Cursor(
            position=position,
            callback=self._append,
        )

    async def _append(self, session: ISession, value: T, position: int):
        await self._on_appended.notify(ValueAppendedEvent(session, value, position))

    async def append(self, session: ISession, value: T):
        await self._append(session, value, -1)

    @property
    def provider_name(self):
        return self._sequencer.provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._sequencer.provider_name = value

    async def setup(self, session: ISession):
        await self._sequencer.setup(session)

    async def cleanup(self, session: ISession):
        await self._sequencer.cleanup(session)

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self
