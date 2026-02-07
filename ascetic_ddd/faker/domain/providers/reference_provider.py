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

    def do_empty(self, clone: typing.Self, shunt: ICloningShunt | None = None):
        super().do_empty(clone, shunt)
        clone._aggregate_provider_accessor = self._aggregate_provider_accessor.empty(shunt)

    def reset(self) -> None:
        super().reset()
        self._aggregate_provider_accessor.reset()

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return

        # Создаём specification с aggregate_provider_accessor для lazy resolve_nested и subqueries
        if self._query is not None:
            specification = self._specification_factory(
                self._query,
                self.aggregate_provider._output_exporter,
                aggregate_provider_accessor=lambda: self.aggregate_provider,
            )
        else:
            specification = EmptySpecification()

        try:
            result = await self._distributor.next(session, specification)
            if result is not None:
                value = self.aggregate_provider._output_exporter(result)
                self.require(self._build_id_query(value))
                self.aggregate_provider.require(dict_to_query(value))
                await self.aggregate_provider.populate(session)
            else:
                # Alternative to "if isinstance(new_query, EqOperator) and new_query.value is None"
                # self._query = None
                self.require({'$eq': None})
            # self.require() could reset self._output
            self._output = result
        except ICursor as cursor:
            if self._query is not None:
                # Propagate constraints to aggregate_provider (already done in require())
                pass
            await self.aggregate_provider.populate(session)
            result = await self.aggregate_provider.create(session)
            await cursor.append(session, result)
            value = self.aggregate_provider._output_exporter(result)
            self.require(self._build_id_query(value))
            # self.require() could reset self._output
            self._output = result

    def _build_id_query(self, exported_value: dict) -> dict:
        """
        Build reference query from exported aggregate value.

        Extracts just the id field for the reference's $rel constraint.
        For scalar PK: {'$rel': {'id': {'$eq': 10}}}
        For composite PK: {'$rel': {'id': {'tenant_id': {'$eq': 15}, ...}}}
        """
        id_attr = self.aggregate_provider._id_attr
        id_value = exported_value[id_attr]
        return {'$rel': {id_attr: dict_to_query(id_value)}}

    async def setup(self, session: ISession):
        await super().setup(session)
        await self._aggregate_provider_accessor.setup(session)

    async def cleanup(self, session: ISession):
        await super().cleanup(session)
        await self._aggregate_provider_accessor.cleanup(session)

    async def create(self, session: ISession) -> T_Output:
        if self._output is None:
            return None
        return await self.aggregate_provider.id_provider.create(session)

    def require(self, query: dict[str, typing.Any]) -> None:
        """
        Set reference provider value using query format.

        Supports all formats:
        - {'$eq': 27} - scalar PK
        - {'tenant_id': {'$eq': 15}, 'local_id': {'$eq': 27}} - composite PK
        - {'$rel': {'is_active': {'$eq': True}}} - related aggregate criteria

        Non-$rel values are automatically wrapped into $rel with id.
        """
        new_query = parse_query(query)

        # EqOperator(None) means "null the reference" - don't wrap, don't merge
        if isinstance(new_query, EqOperator) and new_query.value is None:
            self._query = new_query
            self._propagate_to_aggregate(self._query)
            self._output = None
            self.notify('query', self._query)
            return

        # Wrap non-$rel into $rel with id
        if not isinstance(new_query, RelOperator):
            id_attr = self.aggregate_provider._id_attr
            new_query = RelOperator(CompositeQuery({id_attr: new_query}))

        if self._query is not None:
            # If reference is already explicitly null, don't add constraints
            if self._is_null_reference():
                return
            try:
                self._query = self._query + new_query
            except MergeConflict as e:
                raise DiamondUpdateConflict(e.existing_value, e.new_value, self.provider_name) from e
        else:
            self._query = new_query

        self._propagate_to_aggregate(new_query)
        self._output = empty
        self.notify('query', self._query)

    def _is_null_reference(self) -> bool:
        """
        Check if this reference is explicitly set to null.

        Returns True if _input is EqOperator(None) or RelOperator with id=None.
        """
        if isinstance(self._query, EqOperator) and self._query.value is None:
            return True
        if isinstance(self._query, RelOperator):
            id_attr = self.aggregate_provider._id_attr
            id_constraint = self._query.query.fields.get(id_attr)
            if isinstance(id_constraint, EqOperator) and id_constraint.value is None:
                return True
        return False

    def _propagate_to_aggregate(self, query: IQueryOperator) -> None:
        """
        Propagate $rel constraints to aggregate_provider.

        infinite recursion prevention:
        We only propagate once during require(), not recursively.
        """
        if not isinstance(query, RelOperator):
            return

        for field, op in query.query.fields.items():
            provider = getattr(self.aggregate_provider, field, None)
            if provider is None:
                raise AttributeError(
                    f"Provider '{self.provider_name}': aggregate has no provider '{field}'"
                )
            provider.require(query_to_dict(op))

    @property
    def aggregate_provider(self) -> T_Agg_Provider:
        return self._aggregate_provider_accessor()

    @aggregate_provider.setter
    def aggregate_provider(
            self,
            aggregate_provider: T_Agg_Provider | Callable[[], T_Agg_Provider]
    ) -> None:
        if callable(aggregate_provider):
            aggregate_provider_accessor = LazyAggregateProviderAccessor[T_Input, T_Agg_Provider](aggregate_provider)
        else:
            aggregate_provider_accessor = AggregateProviderAccessor[T_Input, T_Agg_Provider](aggregate_provider)
        self._aggregate_provider_accessor = SubscriptionAggregateProviderAccessor[T_Input, T_Output, T_Agg_Provider](
            self, aggregate_provider_accessor
        )


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
