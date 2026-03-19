import typing
from collections import defaultdict

from ascetic_ddd.faker.domain.sequencers.interfaces import ISequencer
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification

__all__ = ('Sequencer',)

T = typing.TypeVar("T")


class Sequencer(ISequencer):
    _sequences: dict[ISpecification, int]
    _provider_name: str | None = None

    def __init__(self):
        self._sequences = defaultdict(int)

    async def next(
            self,
            session: ISession,
            specification: ISpecification[T],
    ) -> int:
        position = self._sequences[specification]
        self._sequences[specification] += 1
        return position

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        if self._provider_name is None:
            self._provider_name = value

    async def setup(self, session: ISession):
        pass

    async def cleanup(self, session: ISession):
        pass

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self
