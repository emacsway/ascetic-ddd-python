import typing

from ascetic_ddd.faker.domain.fp.factories.interfaces import IFactory
from ascetic_ddd.faker.domain.providers.interfaces import IAggregateRepository
from ascetic_ddd.session.interfaces import ISession

__all__ = ('PersistedFactory',)

T = typing.TypeVar('T')


class PersistedFactory(typing.Generic[T]):
    """Stateless decorator: repository persistence.

    On create:
    1. Delegates to inner.create()
    2. If id_extractor returns non-None, checks repository for existing aggregate
    3. If not found, inserts into repository

    Args:
        inner: Wrapped factory.
        repository: Repository for aggregate persistence.
        id_extractor: Extracts serialized ID from created value for repo lookup.
            Returns None for transient IDs (skip lookup, always insert).
    """

    def __init__(
            self,
            inner: IFactory[T],
            repository: IAggregateRepository[T],
            id_extractor: typing.Callable[[T], typing.Any] | None = None,
    ) -> None:
        self._inner = inner
        self._repository = repository
        self._id_extractor = id_extractor

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> T:
        value = await self._inner.create(session, criteria)
        # Check if aggregate already exists in repository
        if self._id_extractor is not None:
            id_state = self._id_extractor(value)
            if id_state is not None:
                existing = await self._repository.get(session, id_state)
                if existing is not None:
                    return existing
        result = await self._repository.insert(session, value)
        return result if result is not None else value

    async def setup(self, session: ISession) -> None:
        await self._repository.setup(session)
        await self._inner.setup(session)

    async def cleanup(self, session: ISession) -> None:
        await self._repository.cleanup(session)
        await self._inner.cleanup(session)
