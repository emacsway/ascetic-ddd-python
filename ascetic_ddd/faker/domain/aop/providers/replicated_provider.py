import typing

from ascetic_ddd.option import Option, Some, Nothing
from ascetic_ddd.faker.domain.aop.providers.interfaces import IProvider
from ascetic_ddd.faker.domain.distributors.o2m.interfaces import IO2MDistributor
from ascetic_ddd.session.interfaces import ISession

__all__ = ('ReplicatedProvider',)

T = typing.TypeVar('T')


class ReplicatedProvider(typing.Generic[T]):
    """Provider that creates a list of values by populating inner N times.

    Count comes from O2M distributor. AOP equivalent of ReplicatedFactory.

    Args:
        inner: Provider for individual items.
        count_distributor: O2M distributor that determines how many items to create.
    """

    def __init__(
            self,
            inner: IProvider[T],
            count_distributor: IO2MDistributor,
    ) -> None:
        self._inner = inner
        self._count_distributor = count_distributor
        self._output: Option[list[T]] = Nothing()

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return
        count = self._count_distributor.distribute()
        items: list[T] = []
        for _ in range(count):
            await self._inner.populate(session)
            items.append(self._inner.output())
            self._inner.reset()
        self._output = Some(items)

    def output(self) -> list[T]:
        return self._output.unwrap()

    def require(self, criteria: dict[str, typing.Any]) -> None:
        self._inner.require(criteria)
        self._output = Nothing()

    def state(self) -> typing.Any:
        return self._output.unwrap()

    def reset(self, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        self._inner.reset(visited)
        self._output = Nothing()

    def is_complete(self) -> bool:
        return self._output.is_some()

    def is_transient(self) -> bool:
        return False

    async def setup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        await self._inner.setup(session, visited)

    async def cleanup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        await self._inner.cleanup(session, visited)
