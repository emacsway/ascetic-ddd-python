import typing

from ascetic_ddd.option import Option, Some, Nothing
from ascetic_ddd.faker.domain.aop.providers.interfaces import IProvider
from ascetic_ddd.session.interfaces import ISession

__all__ = ('ModeledProvider',)

RawT = typing.TypeVar('RawT')
ModelT = typing.TypeVar('ModelT')


class ModeledProvider(typing.Generic[RawT, ModelT]):
    """Decorator that transforms inner provider output via a factory.

    Wraps an IProvider[RawT] and produces ModelT using:
    - factory: creates domain model from raw data (dict → Model)
    - exporter: serializes domain model back to raw data (Model → dict)
    """

    def __init__(
            self,
            inner: IProvider[RawT],
            factory: typing.Callable[..., ModelT],
            exporter: typing.Callable[[ModelT], RawT],
    ) -> None:
        self._inner = inner
        self._factory = factory
        self._exporter = exporter
        self._output: Option[ModelT] = Nothing()

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return
        await self._inner.populate(session)
        raw = self._inner.output()
        if isinstance(raw, dict):
            self._output = Some(self._factory(**raw))
        else:
            self._output = Some(self._factory(raw))

    def output(self) -> ModelT:
        return self._output.unwrap()

    def require(self, criteria: dict[str, typing.Any]) -> None:
        self._inner.require(criteria)
        self._output = Nothing()

    def state(self) -> typing.Any:
        if self._output.is_some():
            return self._exporter(self._output.unwrap())
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

    async def setup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        await self._inner.setup(session, visited)

    async def cleanup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        await self._inner.cleanup(session, visited)
