import typing

from ascetic_ddd.option import Option, Some, Nothing
from ascetic_ddd.faker.domain.sequencers.interfaces import ISequencer, IStringable
from ascetic_ddd.session.interfaces import ISession

__all__ = ('SequenceProvider',)


class SequenceProvider:
    """Provider that produces sequential integers from a sequencer.

    Supports per-scope sequences via '$scope' in criteria (set via require()).

    Example::

        seq = SequenceProvider(sequencer_factory(name='order.number'))
        await seq.populate(session)
        pos = seq.output()  # 0, 1, 2, ...

        # Per-scope
        seq.require({'$scope': tenant_id})
        await seq.populate(session)
        pos = seq.output()  # 0, 1, 2, ... per tenant

    Args:
        sequencer: Sequencer that provides sequential positions.
    """
    _sequencer: ISequencer
    _output: Option[int]
    _scope: IStringable | None = None

    def __init__(self, sequencer: ISequencer) -> None:
        self._sequencer = sequencer
        self._output = Nothing()
        self._scope = None

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return
        position = await self._sequencer.next(session, self._scope)
        self._output = Some(position)

    def output(self) -> int:
        return self._output.unwrap()

    def require(self, criteria: dict[str, typing.Any]) -> None:
        if '$scope' in criteria:
            self._scope = criteria['$scope']
        self._output = Nothing()

    def state(self) -> typing.Any:
        return self._output.unwrap()

    def reset(self, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        self._output = Nothing()
        self._scope = None

    def is_complete(self) -> bool:
        return self._output.is_some()

    def is_transient(self) -> bool:
        return False

    async def setup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        await self._sequencer.setup(session)

    async def cleanup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        await self._sequencer.cleanup(session)
