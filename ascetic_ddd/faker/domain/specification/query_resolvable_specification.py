"""
Specification built from Query AST.
"""
import typing
from collections.abc import Callable

from ascetic_ddd.faker.domain.providers.interfaces import IReferenceProvider
from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, EqOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.faker.domain.query.visitors import query_to_dict, query_to_plain_value
from ascetic_ddd.faker.domain.specification.interfaces import (
    IResolvableSpecification, ISpecificationVisitor
)
from ascetic_ddd.seedwork.domain.session.interfaces import ISession
from ascetic_ddd.seedwork.domain.utils.data import hashable

__all__ = ('QueryResolvableSpecification',)

T = typing.TypeVar("T", covariant=True)


class QueryResolvableSpecification(IResolvableSpecification[T], typing.Generic[T]):
    """
    Specification built from IQueryOperator tree.

    Requires resolve_nested() call before use to resolve nested FK constraints.

    Supports:
    - $eq: equality check
    - $rel: constraints for related aggregates
    - Nested resolution via resolve_nested()

    Example with operators:
        query = RelOperator(CompositeQuery({
            'status': EqOperator('active'),
            'department': RelOperator(CompositeQuery({'name': EqOperator('IT')}))
        }))
        spec = QueryResolvableSpecification(
            query,
            lambda obj: {'status': obj.status, 'department': obj.department_id},
            aggregate_provider_accessor=lambda: provider
        )

    Example with QueryParser (from QueryResolvableSpecification):
        query = QueryParser().parse({'status_id': {'$rel': {'name': {'$eq': 'Active'}}}})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: {'status_id': obj.status_id, ...},
            aggregate_provider_accessor=lambda: user_provider
        )
        await spec.resolve_nested(session)
        if await spec.is_satisfied_by(session, some_user):
            ...
    """

    _query: IQueryOperator
    _object_exporter: Callable[[T], dict]
    _aggregate_provider_accessor: Callable[[], typing.Any] | None
    _resolved_query: IQueryOperator | None
    _hash: int | None
    _str: str | None

    __slots__ = (
        '_query',
        '_object_exporter',
        '_aggregate_provider_accessor',
        '_resolved_query',
        '_hash',
        '_str',
    )

    def __init__(
        self,
        query: IQueryOperator,
        object_exporter: Callable[[T], dict],
        aggregate_provider_accessor: Callable[[], typing.Any] | None = None,
    ):
        self._query = query
        self._object_exporter = object_exporter
        self._aggregate_provider_accessor = aggregate_provider_accessor
        self._resolved_query = None
        self._hash = None
        self._str = None

    def __str__(self) -> str:
        if self._resolved_query is None:
            raise TypeError(
                "Cannot cast to string unresolved QueryResolvableSpecification. "
                "Call resolve_nested() first."
            )
        if self._str is None:
            pattern = query_to_plain_value(self._resolved_query)
            self._str = str(hashable(pattern))
        return self._str

    def __hash__(self) -> int:
        if self._resolved_query is None:
            raise TypeError(
                "Cannot hash unresolved QueryResolvableSpecification. "
                "Call resolve_nested() first."
            )
        if self._hash is None:
            pattern = query_to_plain_value(self._resolved_query)
            self._hash = hash(hashable(pattern))
        return self._hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QueryResolvableSpecification):
            return False
        if self._resolved_query is None or other._resolved_query is None:
            raise TypeError(
                "Cannot compare unresolved QueryResolvableSpecification. "
                "Call resolve_nested() first."
            )
        return self._resolved_query == other._resolved_query

    async def resolve_nested(self, session: ISession) -> None:
        """
        Resolve $rel constraints into concrete IDs.

        Called by distributor after null-check.
        """
        if self._resolved_query is not None:
            return

        if self._aggregate_provider_accessor is None:
            self._resolved_query = self._query
            return

        self._resolved_query = await self._do_resolve(session, self._query)

    async def _do_resolve(
        self,
        session: ISession,
        query: IQueryOperator
    ) -> IQueryOperator:
        """Resolve nested constraints via ReferenceProviders."""
        if isinstance(query, EqOperator):
            return query

        aggregate_provider = self._aggregate_provider_accessor()
        providers = aggregate_provider.providers if aggregate_provider else {}

        if isinstance(query, RelOperator):
            resolved = await self._resolve_fields(session, query.query.fields, providers)
            return RelOperator(CompositeQuery(resolved))

        if isinstance(query, CompositeQuery):
            resolved = await self._resolve_fields(session, query.fields, providers)
            return CompositeQuery(resolved)

        return query

    async def _resolve_fields(
        self,
        session: ISession,
        fields: dict[str, IQueryOperator],
        providers: dict
    ) -> dict[str, IQueryOperator]:
        """Resolve fields, delegating nested constraints to ReferenceProviders."""
        resolved = {}
        for field, field_op in fields.items():
            provider = providers.get(field)
            if isinstance(provider, IReferenceProvider) and not isinstance(field_op, EqOperator):
                provider.set(query_to_dict(field_op))
                await provider.populate(session)
                resolved[field] = QueryParser().parse(provider.get())
            else:
                resolved[field] = field_op
        return resolved

    async def is_satisfied_by(self, session: ISession, obj: T) -> bool:
        """Check if object satisfies the query."""
        if self._resolved_query is None:
            raise TypeError(
                "Cannot use unresolved QueryResolvableSpecification. "
                "Call resolve_nested() first."
            )

        state = self._object_exporter(obj)
        return self._matches(self._resolved_query, state)

    def _matches(self, query: IQueryOperator, state: typing.Any) -> bool:
        """Check if state matches query."""
        if isinstance(query, EqOperator):
            return state == query.value

        elif isinstance(query, CompositeQuery):
            for field, field_op in query.fields.items():
                if isinstance(state, dict):
                    field_value = state.get(field)
                else:
                    field_value = getattr(state, field, None)
                if not self._matches(field_op, field_value):
                    return False
            return True

        elif isinstance(query, RelOperator):
            return self._matches(query.query, state)

        return False

    def accept(self, visitor: ISpecificationVisitor) -> None:
        """Accept visitor for SQL compilation."""
        visitor.visit_query_specification(
            self._resolved_query or self._query,
            self._aggregate_provider_accessor
        )
