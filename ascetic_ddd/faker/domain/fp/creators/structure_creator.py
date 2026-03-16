import typing

from ascetic_ddd.faker.domain.fp.creators.interfaces import ICreator
from ascetic_ddd.faker.domain.query import parse_query, query_to_dict
from ascetic_ddd.faker.domain.query.operators import CompositeQuery
from ascetic_ddd.session.interfaces import ISession

__all__ = ('StructureCreator',)


class StructureCreator:
    """Stateless composite creator.

    Distributes criteria by field name to children,
    collects results into a dict.
    """

    def __init__(self, **creators: ICreator[typing.Any]) -> None:
        self._creators = creators

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> dict[str, typing.Any]:
        field_criteria = self._distribute_criteria(criteria)
        return {
            name: await creator.create(session, field_criteria.get(name))
            for name, creator in self._creators.items()
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
                if attr in self._creators:
                    result[attr] = query_to_dict(field_query)
        return result

    async def setup(self, session: ISession) -> None:
        for creator in self._creators.values():
            await creator.setup(session)

    async def cleanup(self, session: ISession) -> None:
        for creator in self._creators.values():
            await creator.cleanup(session)
