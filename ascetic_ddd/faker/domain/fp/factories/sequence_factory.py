import typing

from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor, ICursor
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.scope_specification import ScopeSpecification
from ascetic_ddd.session.interfaces import ISession

__all__ = ('SequenceFactory',)


class SequenceFactory:
    """Stateless factory that produces sequential integers.

    Position comes from sequencer (PgSequenceDistributor or SequenceDistributor).
    Supports per-scope sequences via '$scope' in criteria.

    Example::

        # Global sequence
        seq = SequenceFactory(make_distributor(sequence=True, name='order.number'))
        pos = await seq.create(session)  # 0, 1, 2, ...

        # Per-tenant sequence
        pos = await seq.create(session, {'$scope': tenant_id})  # 0, 1, 2, ... per tenant

        # Combined with ModeledFactory for value transform
        factory = ModeledFactory(seq, factory=lambda pos: "ORD-%05d" % pos)

    Args:
        sequencer: M2O distributor that provides sequence positions via ICursor.
    """

    def __init__(self, sequencer: IM2ODistributor[typing.Any]) -> None:
        self._sequencer = sequencer

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> int:
        scope = None
        if criteria is not None:
            scope = criteria.get('$scope')
        spec: ScopeSpecification[typing.Any] | EmptySpecification[typing.Any]
        if scope is not None:
            spec = ScopeSpecification[typing.Any](scope)
        else:
            spec = EmptySpecification[typing.Any]()
        try:
            await self._sequencer.next(session, spec)
        except ICursor as cursor:
            return cursor.position
        # Should not happen — sequence distributors always raise ICursor
        return -1

    async def setup(self, session: ISession) -> None:
        await self._sequencer.setup(session)

    async def cleanup(self, session: ISession) -> None:
        await self._sequencer.cleanup(session)
