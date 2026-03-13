import typing

from ascetic_ddd.option import Option, Some, Nothing
from ascetic_ddd.faker.domain.fp.providers.interfaces import IProvider
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor, ICursor
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.session.interfaces import ISession

__all__ = ('DistributedProvider',)

T = typing.TypeVar('T')


class DistributedProvider(typing.Generic[T]):
    """Decorator that adds distributor-based value selection.

    On populate:
    1. Tries distributor.next() to select an existing value
    2. If found, sets inner provider via require() and populates
    3. On ICursor (distributor exhausted), delegates to inner.populate()
       and appends the new value to distributor via cursor.append()

    The distributor stores state() representations (serializable form),
    not domain objects.
    """

    def __init__(
            self,
            inner: IProvider[T],
            distributor: IM2ODistributor[typing.Any],
    ) -> None:
        self._inner = inner
        self._distributor = distributor
        self._output: Option[T] = Nothing()

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return
        spec = EmptySpecification[typing.Any]()
        try:
            result = await self._distributor.next(session, spec)
            if result.is_some():
                value = result.unwrap()
                # Set inner provider to the distributed value
                if isinstance(value, dict):
                    self._inner.require(value)
                else:
                    self._inner.require({'$eq': value})
                await self._inner.populate(session)
                self._output = Some(self._inner.output())
                return
        except ICursor as cursor:
            # Distributor exhausted — create new value
            await self._inner.populate(session)
            self._output = Some(self._inner.output())
            await cursor.append(session, self._inner.state())
            return
        # next() returned Nothing (e.g. NullableDistributor)
        await self._inner.populate(session)
        self._output = Some(self._inner.output())

    def output(self) -> T:
        return self._output.unwrap()

    def require(self, criteria: dict[str, typing.Any]) -> None:
        self._inner.require(criteria)
        self._output = Nothing()

    def state(self) -> typing.Any:
        return self._inner.state()

    def reset(self, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        self._inner.reset(visited)
        self._output = Nothing()

    def is_complete(self) -> bool:
        return self._output.is_some()

    def is_transient(self) -> bool:
        return self._inner.is_transient()

    async def setup(self, session: ISession) -> None:
        await self._distributor.setup(session)
        await self._inner.setup(session)

    async def cleanup(self, session: ISession) -> None:
        await self._distributor.cleanup(session)
        await self._inner.cleanup(session)
