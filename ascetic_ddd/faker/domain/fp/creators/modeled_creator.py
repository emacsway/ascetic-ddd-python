import typing

from ascetic_ddd.faker.domain.fp.creators.interfaces import ICreator
from ascetic_ddd.session.interfaces import ISession

__all__ = ('ModeledCreator',)

RawT = typing.TypeVar('RawT')
ModelT = typing.TypeVar('ModelT')


class ModeledCreator(typing.Generic[RawT, ModelT]):
    """Stateless decorator: dict -> domain model via factory."""

    def __init__(
            self,
            inner: ICreator[RawT],
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
