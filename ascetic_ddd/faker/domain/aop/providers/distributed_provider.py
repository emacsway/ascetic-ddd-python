import typing

from ascetic_ddd.option import Option, Some, Nothing
from ascetic_ddd.faker.domain.aop.providers.interfaces import IProvider
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor, ICursor
from ascetic_ddd.faker.domain.query import parse_query, query_to_dict
from ascetic_ddd.faker.domain.query.operators import IQueryOperator, MergeConflict
from ascetic_ddd.faker.domain.providers.exceptions import DiamondUpdateConflict
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.query_lookup_specification import QueryLookupSpecification
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.session.interfaces import ISession

__all__ = ('DistributedProvider',)

T = typing.TypeVar('T')


class DistributedProvider(typing.Generic[T]):
    """Decorator that adds distributor-based value selection.

    On populate:
    1. Builds specification from criteria to filter distributor
    2. Tries distributor.next() to select a matching value
    3. If found, sets inner provider via require() and populates
    4. On ICursor (distributor exhausted), delegates to inner.populate()
       and appends the new value to distributor via cursor.append()

    Args:
        inner: Wrapped provider.
        distributor: Distributor for value selection.
        object_exporter: Converts distributor's stored value to state dict
            for specification matching. Defaults to identity.
        aggregate_provider_accessor: Optional callable returning aggregate provider
            for $rel resolution in specification. Required when distributor stores
            FK IDs and criteria contain $rel operators.
    """

    def __init__(
            self,
            inner: IProvider[T],
            distributor: IM2ODistributor[T],
            object_exporter: typing.Callable[[T], typing.Any] | None = None,
            aggregate_provider_accessor: typing.Callable[[], typing.Any] | None = None,
    ) -> None:
        self._inner = inner
        self._distributor = distributor
        self._object_exporter: typing.Callable[[T], typing.Any] = (
            object_exporter if object_exporter is not None else _identity
        )
        self._aggregate_provider_accessor = aggregate_provider_accessor
        self._output: Option[T] = Nothing()
        self._criteria: IQueryOperator | None = None
        self._criteria_propagated: bool = False

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return
        spec = self._make_specification()
        try:
            result = await self._distributor.next(session, spec)
            if result.is_some():
                # Value selected from distributor — use directly.
                # Do NOT propagate to inner via require() to avoid
                # diamond conflicts on shared aggregate providers.
                self._output = Some(result.unwrap())
                return
        except ICursor as cursor:
            # Distributor exhausted — create new value.
            # Propagate criteria to inner for constrained creation
            # (e.g. ReferenceProvider needs to know first_model_id).
            if self._criteria is not None and not self._criteria_propagated:
                self._inner.require(query_to_dict(self._criteria))
                self._criteria_propagated = True
            await self._inner.populate(session)
            output = self._inner.output()
            self._output = Some(output)
            await cursor.append(session, output)
            return
        # next() returned Nothing (e.g. NullableDistributor → null FK)
        self._output = Some(None)  # type: ignore[arg-type]

    def _make_specification(self) -> ISpecification[T]:
        if self._criteria is not None:
            return QueryLookupSpecification[T](
                self._criteria,
                self._object_exporter,
                aggregate_provider_accessor=self._aggregate_provider_accessor,
            )
        return EmptySpecification[T]()

    def output(self) -> T:
        return self._output.unwrap()

    def require(self, criteria: dict[str, typing.Any]) -> None:
        new_criteria = parse_query(criteria)
        if self._criteria is not None:
            try:
                self._criteria = self._criteria + new_criteria
            except MergeConflict as e:
                raise DiamondUpdateConflict(
                    e.existing_value, e.new_value, 'DistributedProvider'
                )
        else:
            self._criteria = new_criteria
        # Criteria is used for distributor specification filtering only.
        # Do NOT forward to inner here — inner receives either:
        # - The selected value (on distributor hit) via require({'$eq': value})
        # - The criteria (on ICursor/creation path) via deferred propagation
        self._output = Nothing()
        self._criteria_propagated = False

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
        self._criteria = None
        self._criteria_propagated = False

    def is_complete(self) -> bool:
        return self._output.is_some()

    def is_transient(self) -> bool:
        return self._inner.is_transient()

    async def setup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        await self._distributor.setup(session)
        await self._inner.setup(session, visited)

    async def cleanup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        await self._distributor.cleanup(session)
        await self._inner.cleanup(session, visited)


def _identity(x: typing.Any) -> typing.Any:
    return x
