import typing
from collections.abc import Callable
from abc import ABCMeta, abstractmethod

from ascetic_ddd.faker.domain.distributors.m2o.interfaces import ICursor, IM2ODistributor
from ascetic_ddd.faker.domain.providers._mixins import BaseDistributionProvider
from ascetic_ddd.faker.domain.providers.exceptions import DiamondUpdateConflict
from ascetic_ddd.faker.domain.providers.interfaces import (
    IReferenceProvider, ICloningShunt, ISetupable, IAggregateProvider,
)
from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, EqOperator, RelOperator, CompositeQuery, MergeConflict
)
from ascetic_ddd.faker.domain.query.parser import parse_query
from ascetic_ddd.faker.domain.query.visitors import query_to_dict, dict_to_query
from ascetic_ddd.option.option import Nothing
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.query_lookup_specification import QueryLookupSpecification
from ascetic_ddd.faker.domain.providers.events import AggregateInsertedEvent, CriteriaRequiredEvent

__all__ = ('ReferenceProvider',)

IdInputT = typing.TypeVar("IdInputT")
IdOutputT = typing.TypeVar("IdOutputT")
AggInputT = typing.TypeVar("AggInputT", bound=dict)
AggOutputT = typing.TypeVar("AggOutputT", bound=object)


class IAggregateProviderAccessor(
    ISetupable,
    typing.Generic[AggInputT, AggOutputT, IdInputT, IdOutputT],
    metaclass=ABCMeta
):
    # TODO: Make resolve() explicitly?
    # TODO: Use Monad, Deferred or Future?

    @abstractmethod
    def __call__(self) -> IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]:
        raise NotImplementedError

    @abstractmethod
    def reset(self, visited: set | None = None):
        raise NotImplementedError

    @abstractmethod
    def clone(self, shunt: ICloningShunt | None = None) -> typing.Self:
        raise NotImplementedError


class ReferenceProvider(
    BaseDistributionProvider[IdInputT, IdOutputT],
    IReferenceProvider[IdInputT, IdOutputT, AggInputT, AggOutputT],
    typing.Generic[IdInputT, IdOutputT, AggInputT, AggOutputT]
):
    _aggregate_provider_accessor: IAggregateProviderAccessor[AggInputT, AggOutputT, IdInputT, IdOutputT]
    _specification_factory: Callable[..., ISpecification]

    def __init__(
            self,
            distributor: IM2ODistributor,
            aggregate_provider: (IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT] |
                                 Callable[[], IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]),
            specification_factory: Callable[..., ISpecification[AggOutputT]] = QueryLookupSpecification[AggOutputT],
    ):
        self.aggregate_provider = aggregate_provider
        self._specification_factory = specification_factory
        super().__init__(distributor=distributor)

    async def create(self, session: ISession) -> IdOutputT:
        if self._output.is_nothing():
            raise RuntimeError("Provider '%s' has no output. Call populate() before create()." % self.provider_name)
        return typing.cast(IdOutputT, self._output.unwrap())

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return

        # Create specification with aggregate_provider_accessor for lazy resolve_nested and subqueries
        if self._criteria is not None:
            specification = self._specification_factory(
                self._criteria,
                self.aggregate_provider._output_exporter,  # type: ignore[attr-defined]
                aggregate_provider_accessor=lambda: self.aggregate_provider,
            )
        else:
            specification = EmptySpecification()

        try:
            result = await self._distributor.next(session, specification)
            if result.is_some():
                agg = result.unwrap()
                agg_state = self.aggregate_provider._output_exporter(agg)  # type: ignore[attr-defined]
                # self.aggregate_provider.require(dict_to_query(agg_state))
                id_ = agg_state[self._id_attr]
                self.aggregate_provider.id_provider.require({'$eq': id_})
                await self.aggregate_provider.populate(session)
                await self.aggregate_provider.create(session)
                # self._set_input(self.aggregate_provider.id_provider.state())
                self._set_input(id_)
                self._set_output(await self.aggregate_provider.id_provider.create(session))
            else:
                # Alternative to "if isinstance(new_criteria, EqOperator) and new_criteria.value is None"
                # self._criteria = None
                self._set_input(None)
                self._set_output(None)
        except ICursor as cursor:
            if self._criteria is not None:
                # Propagate constraints to aggregate_provider (already done in require())
                pass
            await self.aggregate_provider.populate(session)
            created_agg = await self.aggregate_provider.create(session)
            await cursor.append(session, created_agg)
            self._set_input(self.aggregate_provider.id_provider.state())
            # self.require() could reset self._output
            self._set_output(await self.aggregate_provider.id_provider.create(session))

    def require(self, criteria: dict[str, typing.Any]) -> None:
        """
        Set reference provider value using query format.

        Supports all formats:
        - {'$eq': 27} - scalar PK
        - {'tenant_id': {'$eq': 15}, 'local_id': {'$eq': 27}} - composite PK
        - {'$rel': {'is_active': {'$eq': True}}} - related aggregate criteria

        Non-$rel values are automatically wrapped into $rel with id.
        """
        new_criteria = parse_query(criteria)

        # Null FK — no reference. Don't propagate to aggregate.
        if isinstance(new_criteria, EqOperator) and new_criteria.value is None:
            self._set_input(None)
            self._set_output(None)
            return

        old_criteria = self._criteria

        # Wrap non-$rel into $rel with id
        if not isinstance(new_criteria, RelOperator):
            id_attr = self._id_attr
            new_criteria = RelOperator(CompositeQuery({id_attr: new_criteria}))

        if self._criteria is not None:
            try:
                self._criteria = self._criteria + new_criteria
            except MergeConflict as e:
                raise DiamondUpdateConflict(e.existing_value, e.new_value, self.provider_name) from e
        else:
            self._criteria = new_criteria
        # Only reset output if input actually changed
        if self._criteria != old_criteria:
            self._input = Nothing()
            self._output = Nothing()
            self._propagate_to_aggregate(new_criteria)
            self._on_required.notify(CriteriaRequiredEvent(new_criteria))

    def _propagate_to_aggregate(self, criteria: IQueryOperator) -> None:
        """
        Propagate $rel constraints to aggregate_provider.

        infinite recursion prevention:
        We only propagate once during require(), not recursively.
        """
        if isinstance(criteria, RelOperator):
            self.aggregate_provider.require(query_to_dict(criteria.query))

    @property
    def aggregate_provider(self) -> IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]:
        return self._aggregate_provider_accessor()

    @aggregate_provider.setter
    def aggregate_provider(
            self,
            aggregate_provider: (IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT] |
                                 Callable[[], IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]])
    ) -> None:
        if callable(aggregate_provider):
            aggregate_provider_accessor: IAggregateProviderAccessor[
                AggInputT, AggOutputT, IdInputT, IdOutputT
            ] = LazyAggregateProviderAccessor[
                AggInputT, AggOutputT, IdInputT, IdOutputT
            ](aggregate_provider)
        else:
            aggregate_provider_accessor = AggregateProviderAccessor[
                AggInputT, AggOutputT, IdInputT, IdOutputT
            ](aggregate_provider)
        self._aggregate_provider_accessor = SubscriptionAggregateProviderAccessor(
            self, aggregate_provider_accessor
        )

    def _do_clone(self, clone: typing.Self, shunt: ICloningShunt):
        clone._aggregate_provider_accessor = self._aggregate_provider_accessor.clone(shunt)
        super()._do_clone(clone, shunt)

    def _do_reset(self, visited: set) -> None:
        self._aggregate_provider_accessor.reset(visited)
        super()._do_reset(visited)

    @property
    def _id_attr(self) -> str:
        return self.aggregate_provider.id_provider.provider_name.rsplit(".", 1).pop()

    async def setup(self, session: ISession):
        await super().setup(session)
        await self._aggregate_provider_accessor.setup(session)

    async def cleanup(self, session: ISession):
        await super().cleanup(session)
        await self._aggregate_provider_accessor.cleanup(session)


class SubscriptionAggregateProviderAccessor(
    IAggregateProviderAccessor[AggInputT, AggOutputT, IdInputT, IdOutputT],
    typing.Generic[AggInputT, AggOutputT, IdInputT, IdOutputT]
):
    _reference_provider: IReferenceProvider[IdInputT, IdOutputT, AggInputT, AggOutputT]
    _initialized: bool = False
    _delegate: IAggregateProviderAccessor[AggInputT, AggOutputT, IdInputT, IdOutputT]

    def __init__(
            self,
            reference_provider: IReferenceProvider[IdInputT, IdOutputT, AggInputT, AggOutputT],
            delegate: IAggregateProviderAccessor[AggInputT, AggOutputT, IdInputT, IdOutputT]
    ):
        self._reference_provider = reference_provider
        self._delegate = delegate

    def __call__(self) -> IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]:
        aggregate_provider = self._delegate()
        if not self._initialized:

            # Bind repository as external_source for distributor
            self._reference_provider._distributor.bind_external_source(  # type: ignore[attr-defined]
                aggregate_provider.repository
            )

            async def _observer(event: AggregateInsertedEvent):
                # Needed for in-memory distributor and repository.
                # For Pg distributor with external_source — this is a no-op (append checks _external_source).
                await self._reference_provider.append(event.session, event.agg)

            aggregate_provider.repository.on_inserted.attach(
                _observer, self._reference_provider.provider_name
            )

            self._initialized = True

        return aggregate_provider

    def reset(self, visited: set | None = None):
        self._delegate.reset(visited)

    def clone(self, shunt: ICloningShunt | None = None):
        # We do not it for recursion tree
        # Subscription between distributors is one-time, since they are not cloned.
        return self._delegate.clone(shunt)

    async def setup(self, session: ISession):
        await self._delegate.setup(session)

    async def cleanup(self, session: ISession):
        await self._delegate.cleanup(session)


class AggregateProviderAccessor(
    IAggregateProviderAccessor[AggInputT, AggOutputT, IdInputT, IdOutputT],
    typing.Generic[AggInputT, AggOutputT, IdInputT, IdOutputT]
):
    _aggregate_provider: IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]

    def __init__(
            self,
            aggregate_provider: IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]
    ):
        self._aggregate_provider = aggregate_provider

    def __call__(self) -> IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]:
        return self._aggregate_provider

    def reset(self, visited: set | None = None):
        self._aggregate_provider.reset(visited)

    def clone(self, shunt: ICloningShunt | None = None):
        return AggregateProviderAccessor[
            AggInputT, AggOutputT, IdInputT, IdOutputT
        ](self._aggregate_provider.clone(shunt))

    async def setup(self, session: ISession):
        await self._aggregate_provider.setup(session)

    async def cleanup(self, session: ISession):
        await self._aggregate_provider.cleanup(session)


class LazyAggregateProviderAccessor(
    IAggregateProviderAccessor[AggInputT, AggOutputT, IdInputT, IdOutputT],
    typing.Generic[AggInputT, AggOutputT, IdInputT, IdOutputT]
):
    _aggregate_provider: IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT] | None = None
    _aggregate_provider_factory: Callable[[], IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]

    def __init__(
            self,
            aggregate_provider_factory: Callable[[], IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]
    ):
        self._aggregate_provider_factory = aggregate_provider_factory

    def __call__(self) -> IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]:
        if self._aggregate_provider is None:
            self._aggregate_provider = self._aggregate_provider_factory()
        return self._aggregate_provider

    def reset(self, visited: set | None = None):
        self._aggregate_provider = None

    def clone(self, shunt: ICloningShunt | None = None):
        return LazyAggregateProviderAccessor[
            AggInputT, AggOutputT, IdInputT, IdOutputT
        ](self._aggregate_provider_factory)

    async def setup(self, session: ISession):
        if self._aggregate_provider is not None:
            await self._aggregate_provider.setup(session)

    async def cleanup(self, session: ISession):
        if self._aggregate_provider is not None:
            await self._aggregate_provider.cleanup(session)
