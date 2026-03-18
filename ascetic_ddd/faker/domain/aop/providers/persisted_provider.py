import typing

from ascetic_ddd.option import Option, Some, Nothing
from ascetic_ddd.faker.domain.aop.providers.interfaces import IProvider
from ascetic_ddd.faker.domain.providers.interfaces import IAggregateRepository
from ascetic_ddd.session.interfaces import ISession

__all__ = ('PersistedProvider',)

T = typing.TypeVar('T')


class PersistedProvider(typing.Generic[T]):
    """Decorator that adds repository persistence.

    On populate:
    1. If id_provider has a non-transient value, tries repository lookup
    2. If found, uses existing aggregate (skips inner populate)
    3. Otherwise, delegates to inner.populate() and inserts result

    Args:
        inner: Wrapped provider.
        repository: Repository for aggregate persistence.
        id_provider: Reference to the ID provider (same object as in StructureProvider tree).
            Used for repository lookup before creating new aggregates.
    """

    def __init__(
            self,
            inner: IProvider[T],
            repository: IAggregateRepository[T],
            id_provider: IProvider[typing.Any] | None = None,
    ) -> None:
        self._inner = inner
        self._repository = repository
        self._id_provider = id_provider
        self._output: Option[T] = Nothing()

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return
        # Try repository lookup by ID
        if self._id_provider is not None:
            if not self._id_provider.is_complete():
                await self._id_provider.populate(session)
            if self._id_provider.is_complete() and not self._id_provider.is_transient():
                id_state = self._id_provider.state()
                existing = await self._repository.get(session, id_state)
                if existing is not None:
                    self._output = Some(existing)
                    return
        # Populate inner and persist
        await self._inner.populate(session)
        output = self._inner.output()
        result = await self._repository.insert(session, output)
        self._output = Some(result if result is not None else output)

    def output(self) -> T:
        return self._output.unwrap()

    def require(self, criteria: dict[str, typing.Any]) -> None:
        self._inner.require(criteria)
        self._output = Nothing()

    def state(self) -> typing.Any:
        return self._inner.state()

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
        return self._inner.is_transient()

    @property
    def repository(self) -> IAggregateRepository[T]:
        return self._repository

    async def setup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        await self._repository.setup(session)
        await self._inner.setup(session, visited)

    async def cleanup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        await self._repository.cleanup(session)
        await self._inner.cleanup(session, visited)
