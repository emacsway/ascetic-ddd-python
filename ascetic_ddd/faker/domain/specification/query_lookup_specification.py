"""
Query-based lookup specification.
"""
import typing

from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, EqOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.domain.specification.interfaces import ISpecificationVisitor, ISpecification
from ascetic_ddd.seedwork.domain.session import ISession

__all__ = ('QueryLookupSpecification',)


T = typing.TypeVar("T", covariant=True)


class QueryLookupSpecification(ISpecification[T], typing.Generic[T]):
    """
    Specification with nested lookup in is_satisfied_by().

    Unlike QueryResolvableSpecification, does not resolve nested constraints
    upfront, but performs a lookup on each check (with caching).

    Advantages:
    - One index per logical pattern (efficient indexing)
    - New objects are automatically taken into account (lookup at check time)

    Disadvantages:
    - Distribution of nested objects is not considered
    - Requires access to providers during is_satisfied_by()

    Example:
        query = QueryParser().parse({'fk_id': {'$rel': {'status': {'$eq': 'active'}}}})
        spec = QueryLookupSpecification(
            query,
            lambda obj: {'fk_id': obj.fk_id},
            aggregate_provider_accessor=lambda: aggregate_provider
        )
        # One index for all objects with active fk
        # is_satisfied_by() checks fk.status == 'active' via lookup
    """

    _query: IQueryOperator
    _hash: int | None
    _str: str | None
    _object_exporter: typing.Callable[[T], dict]
    _aggregate_provider_accessor: typing.Callable[[], typing.Any] | None
    _nested_cache: dict[tuple[type, str, typing.Any], bool]  # {(provider_type, field_key, fk_id): matches}

    __slots__ = (
        '_query',
        '_object_exporter',
        '_hash',
        '_str',
        '_aggregate_provider_accessor',
        '_nested_cache',
    )

    def __init__(
            self,
            query: IQueryOperator,
            object_exporter: typing.Callable[[T], dict],
            aggregate_provider_accessor: typing.Callable[[], typing.Any] | None = None,
    ):
        self._query = query
        self._object_exporter = object_exporter
        self._aggregate_provider_accessor = aggregate_provider_accessor
        self._hash = None
        self._str = None
        self._nested_cache = {}

    def __str__(self) -> str:
        if self._str is None:
            self._str = repr(self._query)
        return self._str

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(self._query)
        return self._hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QueryLookupSpecification):
            return False
        return self._query == other._query

    async def is_satisfied_by(self, session: ISession, obj: T) -> bool:
        """Check if object satisfies the query."""
        state = self._object_exporter(obj)
        aggregate_provider = self._aggregate_provider_accessor() if self._aggregate_provider_accessor else None
        providers = aggregate_provider.providers if aggregate_provider else {}
        return await self._matches(session, self._query, state, providers)

    async def _matches(
            self,
            session: ISession,
            query: IQueryOperator,
            state: typing.Any,
            providers: dict
    ) -> bool:
        """Check if state matches query, with nested lookup for IReferenceProvider."""
        if isinstance(query, EqOperator):
            return state == query.value

        elif isinstance(query, CompositeQuery):
            if not isinstance(state, dict):
                return False
            for field, field_op in query.fields.items():
                field_value = state.get(field)
                field_provider = providers.get(field)
                if not await self._matches_field(session, field, field_op, field_value, field_provider):
                    return False
            return True

        elif isinstance(query, RelOperator):
            return await self._matches(session, query.query, state, {})

        return False

    async def _matches_field(
            self,
            session: ISession,
            field: str,
            field_op: IQueryOperator,
            field_value: typing.Any,
            provider: typing.Any
    ) -> bool:
        """Match a single field, doing nested lookup if provider is IReferenceProvider."""
        from ascetic_ddd.faker.domain.providers.interfaces import IReferenceProvider

        if isinstance(field_op, EqOperator):
            return field_value == field_op.value

        # Non-EqOperator with IReferenceProvider - need nested lookup
        if isinstance(provider, IReferenceProvider):
            return await self._do_nested_lookup(session, field, field_value, field_op, provider)

        # Non-EqOperator without IReferenceProvider - recursive match
        nested_providers = provider.providers if hasattr(provider, 'providers') else {}
        return await self._matches(session, field_op, field_value, nested_providers)

    async def _do_nested_lookup(
            self,
            session: ISession,
            field_key: str,
            fk_id: typing.Any,
            nested_query: IQueryOperator,
            ref_provider: typing.Any
    ) -> bool:
        """Lookup foreign object and check if it matches nested_query."""
        if fk_id is None:
            return False

        cache_key = (type(ref_provider), field_key, fk_id)
        if cache_key in self._nested_cache:
            return self._nested_cache[cache_key]

        referenced_aggregate_provider = ref_provider.aggregate_provider
        repository = referenced_aggregate_provider._repository
        foreign_obj = await repository.get(session, fk_id)

        if foreign_obj is None:
            result = False
        else:
            foreign_state = referenced_aggregate_provider._output_exporter(foreign_obj)
            foreign_providers = referenced_aggregate_provider.providers
            result = await self._matches(session, nested_query, foreign_state, foreign_providers)

        self._nested_cache[cache_key] = result
        return result

    def accept(self, visitor: ISpecificationVisitor):
        visitor.visit_query_specification(
            self._query,
            self._aggregate_provider_accessor
        )

    def clear_cache(self) -> None:
        """Clears the nested lookup cache."""
        self._nested_cache.clear()
