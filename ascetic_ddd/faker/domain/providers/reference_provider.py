import typing
from collections.abc import Callable
from abc import ABCMeta, abstractmethod

from ascetic_ddd.faker.domain.distributors.m2o.interfaces import ICursor, IM2ODistributor
from ascetic_ddd.faker.domain.providers._mixins import BaseDistributionProvider
from ascetic_ddd.faker.domain.providers.interfaces import (
    IReferenceProvider, IEntityProvider, ICloningShunt, ISetupable
)
from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, EqOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.faker.domain.query.merger import QueryMerger
from ascetic_ddd.faker.domain.query.visitors import query_to_dict, dict_to_query
from ascetic_ddd.seedwork.domain.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.query_resolvable_specification import QueryResolvableSpecification
from ascetic_ddd.faker.domain.values.empty import empty

__all__ = ('ReferenceProvider',)

T_Id_Output = typing.TypeVar("T_Id_Output")
T_Input = typing.TypeVar("T_Input")
T_Output = typing.TypeVar("T_Output")


class IAggregateProviderAccessor(ISetupable, typing.Generic[T_Input, T_Output], metaclass=ABCMeta):
    # TODO: Make resolve() explicitly?
    # TODO: Use Monad, Deferred or Future?

    @abstractmethod
    def __call__(self) -> IEntityProvider[T_Input, T_Output]:
        raise NotImplementedError

    @abstractmethod
    def reset(self):
        raise NotImplementedError

    @abstractmethod
    def empty(self, shunt: ICloningShunt | None = None) -> typing.Self:
        raise NotImplementedError


class ReferenceProvider(
    BaseDistributionProvider[T_Input, T_Output],
    IReferenceProvider[T_Input, T_Output, T_Id_Output],
    typing.Generic[T_Input, T_Output, T_Id_Output]
):
    _aggregate_provider_accessor: IAggregateProviderAccessor[T_Input, T_Output]
    _specification_factory: Callable[..., ISpecification]

    def __init__(
            self,
            distributor: IM2ODistributor,
            aggregate_provider: IEntityProvider[T_Input, T_Output] | Callable[[], IEntityProvider[T_Input, T_Output]],
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
        if self._input is not None:
            specification = self._specification_factory(
                self._input,
                self.aggregate_provider._output_exporter,
                aggregate_provider_accessor=lambda: self.aggregate_provider,
            )
        else:
            specification = EmptySpecification()

        try:
            result = await self._distributor.next(session, specification)
            if result is not None:
                value = self.aggregate_provider._output_exporter(result)
                self.set(self._build_id_query(value))
                self.aggregate_provider.set(dict_to_query(value))
                await self.aggregate_provider.populate(session)
            else:
                # Alternative to "if isinstance(new_query, EqOperator) and new_query.value is None"
                # self._input = None
                self.set({'$eq': None})
            # self.set() could reset self._output
            self._output = result
        except ICursor as cursor:
            if self._input is not None:
                # Propagate constraints to aggregate_provider (already done in set())
                pass
            await self.aggregate_provider.populate(session)
            result = await self.aggregate_provider.create(session)
            await cursor.append(session, result)
            value = self.aggregate_provider._output_exporter(result)
            self.set(self._build_id_query(value))
            # self.set() could reset self._output
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

    async def create(self, session: ISession) -> T_Id_Output:
        if self._output is None:
            return None
        return await self.aggregate_provider.id_provider.create(session)

    def set(self, value: T_Input) -> None:
        """
        Set reference provider value using query format.

        Supports all formats:
        - {'$eq': 27} - scalar PK
        - {'tenant_id': {'$eq': 15}, 'local_id': {'$eq': 27}} - composite PK
        - {'$rel': {'is_active': {'$eq': True}}} - related aggregate criteria

        Non-$rel values are automatically wrapped into $rel with id.
        """
        new_query = QueryParser().parse(value)
        id_attr = self.aggregate_provider._id_attr
        merger = QueryMerger(id_attr=id_attr)

        if self._input is not None:
            # EqOperator(None) means "null the reference" - replace, don't merge
            if isinstance(new_query, EqOperator) and new_query.value is None:
                self._input = new_query
            else:
                self._input = merger.merge(self._input, new_query, self.provider_name)
        else:
            # Wrap non-$rel into $rel
            if not isinstance(new_query, RelOperator):
                if isinstance(new_query, EqOperator):
                    # Scalar PK: {'$eq': 27} -> $rel: {id: {'$eq': 27}}
                    new_query = RelOperator({id_attr: new_query})
                else:
                    # CompositeQuery: {'name': ...} -> $rel: {'name': ...}
                    new_query = RelOperator(new_query.fields)
            self._input = new_query

        self._propagate_to_aggregate(self._input)
        self._output = empty
        self.notify('input', self._input)

    def _propagate_to_aggregate(self, query: IQueryOperator) -> None:
        """
        Propagate $rel constraints to aggregate_provider.

        infinite recursion prevention:
        We only propagate once during set(), not recursively.
        """
        if not isinstance(query, RelOperator):
            return

        for field, op in query.constraints.items():
            provider = getattr(self.aggregate_provider, field, None)
            if provider is None:
                raise AttributeError(
                    f"Provider '{self.provider_name}': aggregate has no provider '{field}'"
                )
            provider.set(query_to_dict(op))

    @property
    def aggregate_provider(self) -> IEntityProvider[T_Input, T_Output]:
        return self._aggregate_provider_accessor()

    @aggregate_provider.setter
    def aggregate_provider(
            self,
            aggregate_provider: IEntityProvider[T_Input, T_Output] | Callable[[], IEntityProvider[T_Input, T_Output]]
    ) -> None:
        if callable(aggregate_provider):
            aggregate_provider_accessor = LazyAggregateProviderAccessor[T_Input, T_Output](aggregate_provider)
        else:
            aggregate_provider_accessor = AggregateProviderAccessor[T_Input, T_Output](aggregate_provider)
        self._aggregate_provider_accessor = SubscriptionAggregateProviderAccessor[T_Input, T_Output, T_Id_Output](
            self, aggregate_provider_accessor
        )


class SubscriptionAggregateProviderAccessor(IAggregateProviderAccessor, typing.Generic[T_Input, T_Output, T_Id_Output]):
    _reference_provider: IReferenceProvider[T_Input, T_Output, T_Id_Output]
    _initialized: bool = False
    _delegate: IAggregateProviderAccessor[T_Input, T_Output]

    def __init__(self,
                 reference_provider: IReferenceProvider[T_Input, T_Output, T_Id_Output],
                 delegate: IAggregateProviderAccessor[T_Input, T_Output]):
        self._reference_provider = reference_provider
        self._delegate = delegate

    def __call__(self) -> IEntityProvider[T_Input, T_Output]:
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


class AggregateProviderAccessor(IAggregateProviderAccessor, typing.Generic[T_Input, T_Output]):
    _aggregate_provider: IEntityProvider[T_Input, T_Output]

    def __init__(self,
                 aggregate_provider: IEntityProvider[T_Input, T_Output]):
        self._aggregate_provider = aggregate_provider

    def __call__(self) -> IEntityProvider[T_Input, T_Output]:
        return self._aggregate_provider

    def empty(self, shunt: ICloningShunt | None = None):
        return AggregateProviderAccessor(self._aggregate_provider.empty(shunt))

    def reset(self):
        self._aggregate_provider.reset()

    async def setup(self, session: ISession):
        await self._aggregate_provider.setup(session)

    async def cleanup(self, session: ISession):
        await self._aggregate_provider.cleanup(session)


class LazyAggregateProviderAccessor(IAggregateProviderAccessor, typing.Generic[T_Input, T_Output]):
    _aggregate_provider: IEntityProvider[T_Input, T_Output] | None = None
    _aggregate_provider_factory: Callable[[], IEntityProvider[T_Input, T_Output]]

    def __init__(self, aggregate_provider_factory: Callable[[], IEntityProvider[T_Input, T_Output]]):
        self._aggregate_provider_factory = aggregate_provider_factory

    def __call__(self) -> IEntityProvider[T_Input, T_Output]:
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
