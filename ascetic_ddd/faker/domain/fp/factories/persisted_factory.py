import typing

from ascetic_ddd.faker.domain.fp.factories.interfaces import IFactory
from ascetic_ddd.faker.domain.query.operators import EqOperator, CompositeQuery
from ascetic_ddd.faker.domain.query.parser import parse_query
from ascetic_ddd.faker.domain.query.visitors import dict_to_query
from ascetic_ddd.faker.domain.providers.interfaces import IAggregateRepository
from ascetic_ddd.session.interfaces import ISession

__all__ = ('PersistedFactory',)

T = typing.TypeVar('T')


class PersistedFactory(typing.Generic[T]):
    """Stateless decorator: repository persistence.

    On create:
    1. If id_factory is set, creates PK from criteria, checks repository
       first — skips inner.create() if aggregate already exists.
       Injects the created PK back into criteria so inner reuses it.
    2. If only id_field is set (no id_factory), extracts scalar $eq ID
       from criteria for repository lookup.
    3. Otherwise, delegates to inner.create() and inserts into repository.

    Args:
        inner: Wrapped factory.
        repository: Repository for aggregate persistence.
        id_field: Field name in criteria that holds the aggregate ID.
        id_factory: Factory for constructing PK ValueObject from criteria.
            Required for composite PKs. For scalar PKs, id_field alone suffices.
        id_exporter: Converts PK ValueObject back to dict for None-check
            and criteria injection. Required when id_factory is set
            for composite PKs.
    """

    def __init__(
            self,
            inner: IFactory[T],
            repository: IAggregateRepository[T],
            id_field: str | None = None,
            id_factory: IFactory[typing.Any] | None = None,
            id_exporter: typing.Callable[[typing.Any], typing.Any] | None = None,
    ) -> None:
        self._inner = inner
        self._repository = repository
        self._id_field = id_field
        self._id_factory = id_factory
        self._id_exporter = id_exporter

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> T:
        if self._id_field is not None and criteria is not None and self._id_field in criteria:
            if self._id_factory is not None:
                # Composite/scalar PK via factory: create ValueObject, check repo, inject back
                id_criteria = criteria[self._id_field]
                id_value = await self._id_factory.create(session, id_criteria)
                id_exported = self._id_exporter(id_value) if self._id_exporter is not None else id_value

                if _is_fully_determined(id_exported):
                    existing = await self._repository.get(session, id_value)
                    if existing is not None:
                        return existing

                # Inject created PK back so inner.create() reuses it
                criteria = {**criteria, self._id_field: dict_to_query(id_exported)}
            else:
                # Scalar PK: extract $eq directly from criteria
                id_value = _try_extract_scalar_id(criteria, self._id_field)
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
        if self._id_factory is not None:
            await self._id_factory.setup(session)

    async def cleanup(self, session: ISession) -> None:
        await self._repository.cleanup(session)
        await self._inner.cleanup(session)
        if self._id_factory is not None:
            await self._id_factory.cleanup(session)


def _try_extract_scalar_id(
        criteria: dict[str, typing.Any],
        id_field: str,
) -> typing.Any:
    """Extract scalar ID value from criteria if it's an explicit $eq.

    Args:
        criteria: Query dict (e.g. {'id': {'$eq': 27}, ...}).
        id_field: Field name to extract.

    Returns:
        The scalar ID value, or None if not found / not scalar $eq.
    """
    parsed = parse_query(criteria)
    if not isinstance(parsed, CompositeQuery) or id_field not in parsed.fields:
        return None
    id_query = parsed.fields[id_field]
    if isinstance(id_query, EqOperator) and id_query.value is not None:
        return id_query.value
    return None


def _is_fully_determined(value: typing.Any) -> bool:
    """Check that exported PK has no None fields, recursively.

    Args:
        value: Exported PK — scalar or (nested) dict.

    Returns:
        True if no None values at any level.
    """
    if value is None:
        return False
    if isinstance(value, dict):
        return all(_is_fully_determined(v) for v in value.values())
    return True
