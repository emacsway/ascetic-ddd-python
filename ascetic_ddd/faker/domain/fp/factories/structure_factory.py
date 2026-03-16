import typing

from ascetic_ddd.faker.domain.fp.factories.interfaces import IFactory
from ascetic_ddd.faker.domain.query import parse_query, query_to_dict
from ascetic_ddd.faker.domain.query.operators import CompositeQuery
from ascetic_ddd.session.interfaces import ISession

__all__ = ('StructureFactory',)


class StructureFactory:
    """Stateless composite factory.

    Distributes criteria by field name to children,
    collects results into a dict.
    """

    def __init__(self, **factories: IFactory[typing.Any]) -> None:
        self._factories = factories

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> dict[str, typing.Any]:
        field_criteria = self._distribute_criteria(criteria)
        return {
            name: await factory.create(session, field_criteria.get(name))
            for name, factory in self._factories.items()
        }

    def _distribute_criteria(
            self,
            criteria: dict[str, typing.Any] | None,
    ) -> dict[str, dict[str, typing.Any] | None]:
        result: dict[str, dict[str, typing.Any] | None] = {}
        if criteria is None:
            return result
        parsed = parse_query(criteria)
        if isinstance(parsed, CompositeQuery):
            for attr, field_query in parsed.fields.items():
                if attr in self._factories:
                    result[attr] = query_to_dict(field_query)
        return result

    async def setup(self, session: ISession) -> None:
        for factory in self._factories.values():
            await factory.setup(session)

    async def cleanup(self, session: ISession) -> None:
        for factory in self._factories.values():
            await factory.cleanup(session)
