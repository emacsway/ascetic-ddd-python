import typing

from ascetic_ddd.faker.domain.fp.factories.interfaces import IFactory
from ascetic_ddd.session.interfaces import ISession

__all__ = ('ModeledFactory',)

RawT = typing.TypeVar('RawT')
ModelT = typing.TypeVar('ModelT')


class ModeledFactory(typing.Generic[RawT, ModelT]):
    """Stateless decorator: dict -> domain model via model factory."""

    def __init__(
            self,
            inner: IFactory[RawT],
            factory: typing.Callable[..., ModelT],
    ) -> None:
        self._inner = inner
        self._factory = factory

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> ModelT:
        raw = await self._inner.create(session, criteria)
        if isinstance(raw, dict):
            return self._factory(**raw)
        return self._factory(raw)

    async def setup(self, session: ISession) -> None:
        await self._inner.setup(session)

    async def cleanup(self, session: ISession) -> None:
        await self._inner.cleanup(session)
