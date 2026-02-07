import typing
from collections.abc import Callable
from abc import ABCMeta, abstractmethod

from ascetic_ddd.faker.domain.distributors.m2o.interfaces import ICursor, IM2ODistributor
from ascetic_ddd.faker.domain.providers._mixins import BaseDistributionProvider
from ascetic_ddd.faker.domain.providers.exceptions import DiamondUpdateConflict
from ascetic_ddd.faker.domain.providers.interfaces import (
    IReferenceProvider, IEntityProvider, ICloningShunt, ISetupable
)
from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, EqOperator, RelOperator, CompositeQuery, MergeConflict
)
from ascetic_ddd.faker.domain.query.parser import parse_query
from ascetic_ddd.faker.domain.query.visitors import query_to_dict, dict_to_query
from ascetic_ddd.seedwork.domain.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.query_resolvable_specification import QueryResolvableSpecification
from ascetic_ddd.faker.domain.values.empty import empty

__all__ = ('ReferenceProvider',)

T_Output = typing.TypeVar("T_Output")
T_Input = typing.TypeVar("T_Input")
T_Agg_Provider = typing.TypeVar("T_Agg_Provider")


class IAggregateProviderAccessor(ISetupable, typing.Generic[T_Agg_Provider], metaclass=ABCMeta):
    # TODO: Make resolve() explicitly?
    # TODO: Use Monad, Deferred or Future?

    @abstractmethod
    def __call__(self) -> T_Agg_Provider:
        raise NotImplementedError

    @abstractmethod
    def reset(self):
        raise NotImplementedError

    @abstractmethod
    def empty(self, shunt: ICloningShunt | None = None) -> typing.Self:
        raise NotImplementedError


class ReferenceProvider(
    BaseDistributionProvider[T_Input, T_Output],
    IReferenceProvider[T_Input, T_Output, T_Agg_Provider],
    typing.Generic[T_Input, T_Output, T_Agg_Provider]
):
    _aggregate_provider_accessor: IAggregateProviderAccessor[T_Agg_Provider]
    _specification_factory: Callable[..., ISpecification]

    def __init__(
            self,
            distributor: IM2ODistributor,
            aggregate_provider: T_Agg_Provider | Callable[[], T_Agg_Provider],
            specification_factory: Callable[..., ISpecification] = QueryResolvableSpecification,
    ):
        self.aggregate_provider = aggregate_provider
        self._specification_factory = specification_factory
        super().__init__(distributor=distributor)

    async def create(self, session: ISession) -> T_Output:
        if self._output is empty:
            raise RuntimeError("Provider '%s' has no output. Call populate() before create()." % self.provider_name)
        return self._output

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return

        # Создаём specification с aggregate_provider_accessor для lazy resolve_nested и subqueries
        if self._criteria is not None:
            specification = self._specification_factory(
                self._criteria,
                self.aggregate_provider._output_exporter,
                aggregate_provider_accessor=lambda: self.aggregate_provider,
            )
        else:
            specification = EmptySpecification()

        try:
            output = await self._distributor.next(session, specification)
            if output is not None:
                input_ = self.aggregate_provider._output_exporter(output)
                self.aggregate_provider.require(dict_to_query(input_))
                await self.aggregate_provider.populate(session)
                self._set_input(self.aggregate_provider.id_provider.state())
                self._output = await self.aggregate_provider.id_provider.create(session)
            else:
                # Alternative to "if isinstance(new_criteria, EqOperator) and new_criteria.value is None"
                # self._criteria = None
                self._set_input(None)
            # self.require() could reset self._output
            self._output = output
        except ICursor as cursor:
            if self._criteria is not None:
                # Propagate constraints to aggregate_provider (already done in require())
                pass
            await self.aggregate_provider.populate(session)
            output = await self.aggregate_provider.create(session)
            await cursor.append(session, output)
            self._set_input(self.aggregate_provider.id_provider.state())
            # self.require() could reset self._output
            self._output = await self.aggregate_provider.id_provider.create(session)

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
        old_criteria = self._criteria

        # Wrap non-$rel into $rel with id
        if not isinstance(new_criteria, RelOperator):
            id_attr = self.aggregate_provider._id_attr
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
            self._input = empty
            self._output = empty
            self._propagate_to_aggregate(new_criteria)
            self.notify('criteria', new_criteria)

    def _propagate_to_aggregate(self, criteria: IQueryOperator) -> None:
        """
        Propagate $rel constraints to aggregate_provider.

        infinite recursion prevention:
        We only propagate once during require(), not recursively.
        """
        if isinstance(criteria, RelOperator):
            self.aggregate_provider.require(query_to_dict(criteria.query))

    @property
    def aggregate_provider(self) -> T_Agg_Provider:
        return self._aggregate_provider_accessor()

    @aggregate_provider.setter
    def aggregate_provider(
            self,
            aggregate_provider: T_Agg_Provider | Callable[[], T_Agg_Provider]
    ) -> None:
        if callable(aggregate_provider):
            aggregate_provider_accessor = LazyAggregateProviderAccessor[T_Agg_Provider](aggregate_provider)
        else:
            aggregate_provider_accessor = AggregateProviderAccessor[T_Agg_Provider](aggregate_provider)
        self._aggregate_provider_accessor = SubscriptionAggregateProviderAccessor[T_Input, T_Output, T_Agg_Provider](
            self, aggregate_provider_accessor
        )

    def do_empty(self, clone: typing.Self, shunt: ICloningShunt | None = None):
        super().do_empty(clone, shunt)
        clone._aggregate_provider_accessor = self._aggregate_provider_accessor.empty(shunt)

    def reset(self) -> None:
        super().reset()
        self._aggregate_provider_accessor.reset()

    async def setup(self, session: ISession):
        await super().setup(session)
        await self._aggregate_provider_accessor.setup(session)

    async def cleanup(self, session: ISession):
        await super().cleanup(session)
        await self._aggregate_provider_accessor.cleanup(session)


class SubscriptionAggregateProviderAccessor(IAggregateProviderAccessor[T_Agg_Provider], typing.Generic[T_Input, T_Output, T_Agg_Provider]):
    _reference_provider: IReferenceProvider[T_Input, T_Output, T_Agg_Provider]
    _initialized: bool = False
    _delegate: IAggregateProviderAccessor[T_Agg_Provider]

    def __init__(self,
                 reference_provider: IReferenceProvider[T_Input, T_Output, T_Agg_Provider],
                 delegate: IAggregateProviderAccessor[T_Agg_Provider]):
        self._reference_provider = reference_provider
        self._delegate = delegate

    def __call__(self) -> T_Agg_Provider:
        aggregate_provider = self._delegate()
        if not self._initialized:

            # Привязываем repository как external_source для distributor
            if hasattr(aggregate_provider, '_repository'):
                self._reference_provider._distributor.bind_external_source(
                    aggregate_provider._repository
                )

            async def _observer(aspect, session, agg):
                # Нужна для in-memory distributor and repository.
                # Для Pg distributor с external_source — это no-op (append проверяет _external_source).
                await self._reference_provider.append(session, agg)

            aggregate_provider.attach(
                'repository.value', _observer, self._reference_provider.provider_name
            )

            self._initialized = True

        return aggregate_provider

    def empty(self, shunt: ICloningShunt | None = None):
        # We do not it for recursion tree
        # Подписка между distributors однократная, т.к. они не клонируются.
        return self._delegate.empty(shunt)

    def reset(self):
        self._delegate.reset()

    async def setup(self, session: ISession):
        await self._delegate.setup(session)

    async def cleanup(self, session: ISession):
        await self._delegate.cleanup(session)


class AggregateProviderAccessor(IAggregateProviderAccessor[T_Agg_Provider], typing.Generic[T_Agg_Provider]):
    _aggregate_provider: T_Agg_Provider

    def __init__(self,
                 aggregate_provider: T_Agg_Provider):
        self._aggregate_provider = aggregate_provider

    def __call__(self) -> T_Agg_Provider:
        return self._aggregate_provider

    def empty(self, shunt: ICloningShunt | None = None):
        return AggregateProviderAccessor(self._aggregate_provider.empty(shunt))

    def reset(self):
        self._aggregate_provider.reset()

    async def setup(self, session: ISession):
        await self._aggregate_provider.setup(session)

    async def cleanup(self, session: ISession):
        await self._aggregate_provider.cleanup(session)


class LazyAggregateProviderAccessor(IAggregateProviderAccessor[T_Agg_Provider], typing.Generic[T_Agg_Provider]):
    _aggregate_provider: T_Agg_Provider | None = None
    _aggregate_provider_factory: Callable[[], T_Agg_Provider]

    def __init__(self, aggregate_provider_factory: Callable[[], T_Agg_Provider]):
        self._aggregate_provider_factory = aggregate_provider_factory

    def __call__(self) -> T_Agg_Provider:
        if self._aggregate_provider is None:
            self._aggregate_provider = self._aggregate_provider_factory()
        return self._aggregate_provider

    def empty(self, shunt: ICloningShunt | None = None):
        return LazyAggregateProviderAccessor(self._aggregate_provider_factory)

    def reset(self):
        self._aggregate_provider = None

    async def setup(self, session: ISession):
        if self._aggregate_provider is not None:
            await self._aggregate_provider.setup(session)

    async def cleanup(self, session: ISession):
        if self._aggregate_provider is not None:
            await self._aggregate_provider.cleanup(session)
