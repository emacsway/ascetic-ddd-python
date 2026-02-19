import typing

from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.signals.signal import AsyncSignal
from ascetic_ddd.faker.domain.distributors.m2o.events import ValueAppendedEvent
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification

__all__ = ('DummyDistributor',)

T = typing.TypeVar("T")


class DummyDistributor(IM2ODistributor[T], typing.Generic[T]):
    _provider_name: str | None = None
    _on_appended: IAsyncSignal[ValueAppendedEvent[T]]

    def __init__(self):
        self._on_appended = AsyncSignal[ValueAppendedEvent[T]]()

    @property
    def on_appended(self) -> IAsyncSignal[ValueAppendedEvent[T]]:
        return self._on_appended

    async def next(
            self,
            session: ISession,
            specification: ISpecification[T] | None = None,
    ) -> T:
        raise Cursor(
            position=-1,
            callback=self._append,
        )

    async def _append(self, session: ISession, value: T, position: int):
        await self._on_appended.notify(ValueAppendedEvent(session, value, position))

    async def append(self, session: ISession, value: T):
        await self._append(session, value, -1)

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        if self._provider_name is None:
            self._provider_name = value

    async def setup(self, session: ISession):
        pass

    async def cleanup(self, session: ISession):
        pass

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self

    def bind_external_source(self, external_source: typing.Any) -> None:
        """DummyDistributor does not use external_source."""
        pass
