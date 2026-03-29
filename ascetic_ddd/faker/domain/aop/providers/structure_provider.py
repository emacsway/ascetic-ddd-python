import typing

from ascetic_ddd.option import Option, Some, Nothing
from ascetic_ddd.faker.domain.aop.providers.interfaces import IProvider
from ascetic_ddd.faker.domain.query import parse_query, query_to_dict
from ascetic_ddd.faker.domain.query.evaluate_visitor import EvaluateWalker
from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, CompositeQuery, MergeConflict,
)
from ascetic_ddd.faker.domain.providers.exceptions import DiamondUpdateConflict
from ascetic_ddd.session.interfaces import ISession


__all__ = ('StructureProvider',)



class StructureProvider:
    """Composite provider that composes named child providers into a dict.

    Distributes require() criteria by field name to children.
    Collects output() from all children into a single dict.
    """

    def __init__(self, **providers: IProvider[typing.Any]) -> None:
        self._providers: dict[str, IProvider[typing.Any]] = providers
        self._output: Option[dict[str, typing.Any]] = Nothing()
        self._criteria: IQueryOperator | None = None

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return
        for provider in self._providers.values():
            if not provider.is_complete():
                await provider.populate(session)
        result = {
            name: provider.output()
            for name, provider in self._providers.items()
        }
        self._output = Some(result)

    def output(self) -> dict[str, typing.Any]:
        return self._output.unwrap()

    def require(self, criteria: dict[str, typing.Any]) -> None:
        new_criteria = parse_query(criteria)
        old_criteria = self._criteria
        if self._criteria is not None:
            try:
                self._criteria = self._criteria + new_criteria
            except MergeConflict as e:
                raise DiamondUpdateConflict(
                    e.existing_value, e.new_value, 'StructureProvider'
                )
        else:
            self._criteria = new_criteria

        if self._criteria != old_criteria:
            if self._output.is_some():
                if not self.is_transient():
                    state = self.state()
                    walker = EvaluateWalker()
                    if not walker.evaluate_sync(new_criteria, state):
                        raise DiamondUpdateConflict(state, query_to_dict(new_criteria), 'StructureProvider')
                else:
                    self._output = Nothing()

            self._distribute_criteria(new_criteria)

    def _distribute_criteria(self, query: IQueryOperator) -> None:
        if isinstance(query, CompositeQuery):
            for attr, field_query in query.fields.items():
                if attr in self._providers:
                    self._providers[attr].require(query_to_dict(field_query))

    def state(self) -> dict[str, typing.Any]:
        return {
            name: provider.state()
            for name, provider in self._providers.items()
        }

    def reset(self, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        for provider in self._providers.values():
            provider.reset(visited)
        self._output = Nothing()
        self._criteria = None

    def is_complete(self) -> bool:
        return self._output.is_some()

    def is_transient(self) -> bool:
        return any(provider.is_transient() for provider in self._providers.values())

    @property
    def providers(self) -> dict[str, IProvider[typing.Any]]:
        return self._providers

    async def setup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        for provider in self._providers.values():
            await provider.setup(session, visited)

    async def cleanup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        for provider in self._providers.values():
            await provider.cleanup(session, visited)
