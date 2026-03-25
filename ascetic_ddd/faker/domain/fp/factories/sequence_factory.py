import typing

from ascetic_ddd.faker.domain.sequencers.interfaces import ISequencer
from ascetic_ddd.session.interfaces import ISession

__all__ = ('SequenceFactory',)


class SequenceFactory:
    """Stateless factory that produces sequential integers.

    Position comes from sequencer (Sequencer or PgSequencer).
    Supports per-scope sequences via '$scope' in criteria.

    Example::

        # Global sequence
        seq = SequenceFactory(sequencer_factory(name='order.number'))
        pos = await seq.create(session)  # 0, 1, 2, ...

        # Per-tenant sequence
        pos = await seq.create(session, {'$scope': tenant_id})  # 0, 1, 2, ... per tenant

        # Combined with ModeledFactory for value transform
        factory = ModeledFactory(seq, factory=lambda pos: "ORD-%05d" % pos)

    Args:
        sequencer: Sequencer that provides sequential positions.
    """

    def __init__(self, sequencer: ISequencer) -> None:
        self._sequencer = sequencer

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> int:
        scope = None
        if criteria is not None:
            scope = criteria.get('$scope')
        return await self._sequencer.next(session, scope)

    async def setup(self, session: ISession) -> None:
        await self._sequencer.setup(session)

    async def cleanup(self, session: ISession) -> None:
        await self._sequencer.cleanup(session)
