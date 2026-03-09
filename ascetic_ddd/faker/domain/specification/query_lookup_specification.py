"""
Query-based lookup specification.
"""
import typing

from ascetic_ddd.faker.domain.query.operators import IQueryOperator
from ascetic_ddd.faker.domain.query.evaluate_visitor import EvaluateWalker
from ascetic_ddd.faker.domain.specification.interfaces import ISpecificationVisitor, ISpecification
from ascetic_ddd.faker.domain.specification.object_resolver import ProviderObjectResolver
from ascetic_ddd.session.interfaces import ISession

__all__ = ('QueryLookupSpecification',)


T = typing.TypeVar("T")


class QueryLookupSpecification(ISpecification[T], typing.Generic[T]):
    """
    Specification with nested lookup in is_satisfied_by().

    Unlike QueryResolvableSpecification, does not resolve nested constraints
    upfront, but performs a lookup on each check (via EvaluateWalker).

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
            aggregate_provider_accessor=lambda: aggregate_provider,
        )
        # One index for all objects with active fk
        # is_satisfied_by() checks fk.status == 'active' via lookup

    object_exporter converts distributor object to state for matching.
    aggregate_provider_accessor enables $rel resolution via EvaluateWalker.
    """

    _query: IQueryOperator
    _hash: int | None
    _str: str | None
    _object_exporter: typing.Callable[[T], typing.Any]
    _aggregate_provider_accessor: typing.Callable[[], typing.Any] | None

    __slots__ = (
        '_query',
        '_object_exporter',
        '_hash',
        '_str',
        '_aggregate_provider_accessor',
    )

    def __init__(
            self,
            query: IQueryOperator,
            object_exporter: typing.Callable[[T], typing.Any],
            aggregate_provider_accessor: typing.Callable[[], typing.Any] | None = None,
    ):
        self._query = query
        self._object_exporter = object_exporter
        self._aggregate_provider_accessor = aggregate_provider_accessor
        self._hash = None
        self._str = None

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
        resolver: ProviderObjectResolver | None = (
            ProviderObjectResolver(self._aggregate_provider_accessor) if self._aggregate_provider_accessor else None
        )
        walker = EvaluateWalker(resolver)
        return await walker.evaluate(session, self._query, state)

    def accept(self, visitor: ISpecificationVisitor):
        visitor.visit_query_specification(
            self._query,
            self._aggregate_provider_accessor
        )
