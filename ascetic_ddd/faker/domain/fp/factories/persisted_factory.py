import typing

from ascetic_ddd.faker.domain.fp.factories.interfaces import IFactory
from ascetic_ddd.faker.domain.query.operators import EqOperator, CompositeQuery
from ascetic_ddd.faker.domain.query.parser import parse_query
from ascetic_ddd.faker.domain.providers.interfaces import IAggregateRepository
from ascetic_ddd.session.interfaces import ISession

__all__ = ('PersistedFactory',)

T = typing.TypeVar('T')


class PersistedFactory(typing.Generic[T]):
    """Stateless decorator: repository persistence.

    On create:
    1. If id_field is set and criteria contains an explicit $eq for that field,
       checks repository first — skips inner.create() if aggregate already exists.
    2. Otherwise, delegates to inner.create() and inserts into repository.

    Args:
        inner: Wrapped factory.
        repository: Repository for aggregate persistence.
        id_field: Field name in criteria that holds the aggregate ID.
            When set, enables early repository lookup from criteria
            before delegating to inner.create().
    """

    def __init__(
            self,
            inner: IFactory[T],
            repository: IAggregateRepository[T],
            id_field: str | None = None,
    ) -> None:
        self._inner = inner
        self._repository = repository
        self._id_field = id_field

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> T:
        # Short-circuit: extract ID from criteria, check repo before inner.create()
        if self._id_field is not None and criteria is not None:
            id_value = _try_extract_id(criteria, self._id_field)
            if id_value is not None:
                existing = await self._repository.get(session, id_value)
                if existing is not None:
                    return existing
        value = await self._inner.create(session, criteria)
        result = await self._repository.insert(session, value)
        return result if result is not None else value

    async def setup(self, session: ISession) -> None:
        await self._repository.setup(session)
        await self._inner.setup(session)

    async def cleanup(self, session: ISession) -> None:
        await self._repository.cleanup(session)
        await self._inner.cleanup(session)


def _try_extract_id(
        criteria: dict[str, typing.Any],
        id_field: str,
) -> typing.Any:
    """Extract ID value from criteria if it's an explicit $eq.

    Args:
        criteria: Query dict (e.g. {'id': {'$eq': 27}, ...}).
        id_field: Field name to extract.

    Returns:
        The ID value if found, None otherwise.
    """
    parsed = parse_query(criteria)
    if isinstance(parsed, CompositeQuery) and id_field in parsed.fields:
        id_query = parsed.fields[id_field]
        if isinstance(id_query, EqOperator) and id_query.value is not None:
            return id_query.value
    return None
