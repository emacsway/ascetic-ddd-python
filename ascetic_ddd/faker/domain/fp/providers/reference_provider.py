import typing
from collections.abc import Callable

from ascetic_ddd.option import Option, Some, Nothing
from ascetic_ddd.faker.domain.fp.providers.interfaces import IProvider
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor, ICursor
from ascetic_ddd.faker.domain.query import parse_query, query_to_dict
from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, EqOperator, RelOperator, MergeConflict,
)
from ascetic_ddd.faker.domain.providers.exceptions import DiamondUpdateConflict
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.query_lookup_specification import QueryLookupSpecification
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.session.interfaces import ISession

__all__ = ('ReferenceProvider',)

IdT = typing.TypeVar('IdT')


class ReferenceProvider(typing.Generic[IdT]):
    """FK reference provider for M:1 relationships.

    Produces FK IDs by selecting from distributor (existing aggregate)
    or creating new aggregate via aggregate_provider (on distributor exhaustion).

    Supports require() formats:
    - {'$eq': 27} — scalar FK
    - {'tenant_id': ..., 'local_id': ...} — composite FK
    - {'$rel': {'status': {'$eq': 'active'}}} — constraints on related aggregate

    Args:
        distributor: Distributor for FK ID selection.
        aggregate_provider: Referenced aggregate provider, or callable factory
            for lazy resolution (cyclic dependencies).
        id_attr: Field name to extract ID from aggregate state.
        object_exporter: Converts distributor's stored ID value to state dict
            for specification matching. Defaults to identity.
    """

    def __init__(
            self,
            distributor: IM2ODistributor[IdT],
            aggregate_provider: 'IProvider[typing.Any] | Callable[[], IProvider[typing.Any]]',
            id_attr: str = 'id',
            object_exporter: Callable[[IdT], typing.Any] | None = None,
    ) -> None:
        self._distributor = distributor
        self._id_attr = id_attr
        self._object_exporter: Callable[[IdT], typing.Any] = (
            object_exporter if object_exporter is not None else _identity
        )
        self._output: Option[IdT | None] = Nothing()
        self._criteria: IQueryOperator | None = None
        self._is_transient: bool = False
        # Lazy (callable factory) or eager (provider instance) resolution.
        # Provider instances have populate attribute; plain callables do not.
        if callable(aggregate_provider) and not hasattr(aggregate_provider, 'populate'):
            self._aggregate_provider_factory: Callable[[], IProvider[typing.Any]] | None = aggregate_provider
            self._aggregate_provider: IProvider[typing.Any] | None = None
        else:
            self._aggregate_provider_factory = None
            self._aggregate_provider = typing.cast(IProvider[typing.Any], aggregate_provider)

    @property
    def aggregate_provider(self) -> 'IProvider[typing.Any]':
        if self._aggregate_provider is None:
            assert self._aggregate_provider_factory is not None
            self._aggregate_provider = self._aggregate_provider_factory()
        return self._aggregate_provider

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return

        spec = self._make_specification()
        try:
            result = await self._distributor.next(session, spec)
            if result.is_some():
                id_value = result.unwrap()
                self._output = Some(id_value)
                self._is_transient = False
                # Set aggregate provider's ID so it can be looked up
                agg = self.aggregate_provider
                agg.require({self._id_attr: id_value})
                await agg.populate(session)
                return
            # next() returned Nothing (e.g. NullableDistributor)
            self._output = Some(None)
            self._is_transient = False
            return
        except ICursor as cursor:
            # Distributor exhausted — create new aggregate
            agg = self.aggregate_provider
            await agg.populate(session)
            id_value = self._extract_id(agg)
            self._output = Some(id_value)
            self._is_transient = False
            await cursor.append(session, id_value)

    def _make_specification(self) -> ISpecification[IdT]:
        if self._criteria is not None:
            return QueryLookupSpecification[IdT](
                self._criteria,
                self._object_exporter,
                aggregate_provider_accessor=lambda: self.aggregate_provider,
            )
        return EmptySpecification[IdT]()

    def _extract_id(self, agg_provider: 'IProvider[typing.Any]') -> typing.Any:
        state = agg_provider.state()
        if isinstance(state, dict) and self._id_attr in state:
            return state[self._id_attr]
        return state

    def output(self) -> IdT:
        return self._output.unwrap()  # type: ignore[return-value]

    def require(self, criteria: dict[str, typing.Any]) -> None:
        new_criteria = parse_query(criteria)

        # Null FK — no reference
        if isinstance(new_criteria, EqOperator) and new_criteria.value is None:
            self._output = Some(None)
            self._is_transient = False
            return

        old_criteria = self._criteria

        if self._criteria is not None:
            try:
                self._criteria = self._criteria + new_criteria
            except MergeConflict as e:
                raise DiamondUpdateConflict(
                    e.existing_value, e.new_value, 'ReferenceProvider'
                )
        else:
            self._criteria = new_criteria

        if self._criteria != old_criteria:
            self._output = Nothing()
            self._propagate_to_aggregate(new_criteria)

    def _propagate_to_aggregate(self, criteria: IQueryOperator) -> None:
        """Propagate constraints to aggregate_provider.

        - $rel criteria -> propagate to aggregate_provider (field-level constraints)
        - ID criteria -> propagate to aggregate_provider's ID field
        """
        if isinstance(criteria, RelOperator):
            self.aggregate_provider.require(query_to_dict(criteria.query))
        else:
            self.aggregate_provider.require(
                {self._id_attr: query_to_dict(criteria)}
            )

    def state(self) -> typing.Any:
        return self._output.unwrap()

    def reset(self, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        self._output = Nothing()
        self._criteria = None
        self._is_transient = False
        if self._aggregate_provider is not None:
            self._aggregate_provider.reset(visited)
        # Reset lazy accessor for next resolution
        if self._aggregate_provider_factory is not None:
            self._aggregate_provider = None

    def is_complete(self) -> bool:
        return self._output.is_some()

    def is_transient(self) -> bool:
        return self._is_transient

    async def setup(self, session: ISession) -> None:
        await self._distributor.setup(session)
        await self.aggregate_provider.setup(session)

    async def cleanup(self, session: ISession) -> None:
        await self._distributor.cleanup(session)
        if self._aggregate_provider is not None:
            await self._aggregate_provider.cleanup(session)


def _identity(x: typing.Any) -> typing.Any:
    return x
