import typing

from ascetic_ddd.faker.domain.fp.factories.interfaces import IFactory
from ascetic_ddd.faker.domain.distributors.o2m.interfaces import IO2MDistributor
from ascetic_ddd.session.interfaces import ISession

__all__ = ('ReplicatedFactory',)

T = typing.TypeVar('T')


class ReplicatedFactory(typing.Generic[T]):
    """Stateless factory that creates a list of values.

    Calls inner.create() N times, where N comes from O2M distributor.
    FP equivalent of replicateM.

    Args:
        inner: Factory for individual items.
        count_distributor: O2M distributor that determines how many items to create.
    """

    def __init__(
            self,
            inner: IFactory[T],
            count_distributor: IO2MDistributor,
    ) -> None:
        self._inner = inner
        self._count_distributor = count_distributor

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> list[T]:
        count = self._count_distributor.distribute()
        return [
            await self._inner.create(session, criteria)
            for _ in range(count)
        ]

    async def setup(self, session: ISession) -> None:
        await self._inner.setup(session)

    async def cleanup(self, session: ISession) -> None:
        await self._inner.cleanup(session)
