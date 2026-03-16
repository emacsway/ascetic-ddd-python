import typing

from ascetic_ddd.faker.domain.fp.creators.interfaces import ICreator
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor, ICursor
from ascetic_ddd.faker.domain.query import parse_query
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.query_lookup_specification import QueryLookupSpecification
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.session.interfaces import ISession

__all__ = ('DistributedCreator',)

T = typing.TypeVar('T')


class DistributedCreator(typing.Generic[T]):
    """Stateless decorator: distributor-based value selection.

    On create:
    1. Builds specification from criteria
    2. Tries distributor.next() — returns existing value on hit
    3. On ICursor (exhausted) — delegates to inner.create(), appends result
    4. On Nothing (NullableDistributor) — returns None
    """

    def __init__(
            self,
            inner: ICreator[T],
            distributor: IM2ODistributor[T],
            object_exporter: typing.Callable[[T], typing.Any] | None = None,
    ) -> None:
        self._inner = inner
        self._distributor = distributor
        self._object_exporter: typing.Callable[[T], typing.Any] = (
            object_exporter if object_exporter is not None else _identity
        )

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> T | None:
        spec = self._make_specification(criteria)
        try:
            result = await self._distributor.next(session, spec)
            if result.is_some():
                return result.unwrap()
        except ICursor as cursor:
            value = await self._inner.create(session, criteria)
            await cursor.append(session, value)
            return value
        # Nothing from NullableDistributor
        return None

    def _make_specification(
            self,
            criteria: dict[str, typing.Any] | None,
    ) -> ISpecification[T]:
        if criteria is not None:
            query = parse_query(criteria)
            return QueryLookupSpecification[T](query, self._object_exporter)
        return EmptySpecification[T]()

    async def setup(self, session: ISession) -> None:
        await self._distributor.setup(session)
        await self._inner.setup(session)

    async def cleanup(self, session: ISession) -> None:
        await self._distributor.cleanup(session)
        await self._inner.cleanup(session)


def _identity(x: typing.Any) -> typing.Any:
    return x
