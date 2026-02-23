import typing
from abc import ABCMeta, abstractmethod
from collections.abc import Callable

from ascetic_ddd.faker.domain.distributors.o2m.interfaces import IO2MDistributor
from ascetic_ddd.faker.domain.distributors.o2m.weighted_range_distributor import WeightedRangeDistributor
from ascetic_ddd.faker.domain.providers._mixins import (
    NameableMixin, LifecycleAbleMixin
)
from ascetic_ddd.signals.interfaces import ISyncSignal
from ascetic_ddd.signals.signal import SyncSignal
from ascetic_ddd.faker.domain.providers.events import DependentCriteriaRequiredEvent, InputPopulatedEvent
from ascetic_ddd.faker.domain.providers.interfaces import (
    IDependentProvider, ICloningShunt, ISetupable,
    IAggregateProvider,
)
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.values.empty import empty, Empty

__all__ = ('DependentProvider',)


IdInputT = typing.TypeVar("IdInputT")
IdOutputT = typing.TypeVar("IdOutputT")
AggInputT = typing.TypeVar("AggInputT", bound=dict)
AggOutputT = typing.TypeVar("AggOutputT", bound=object)


class IAggregateProvidersAccessor(
    ISetupable,
    typing.Generic[AggInputT, AggOutputT, IdInputT, IdOutputT],
    metaclass=ABCMeta
):
    """
    Accessor for managing list of aggregate providers.
    Supports lazy resolution and cloning.
    """

    @abstractmethod
    def __call__(self, count: int) -> list[IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]:
        """
        Returns list of aggregate providers for creating N children.
        Creates/clones providers if needed to match the requested count.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self, visited: set | None = None):
        raise NotImplementedError

    @abstractmethod
    def clone(self, shunt: ICloningShunt | None = None) -> typing.Self:
        raise NotImplementedError


class DependentProvider(
    NameableMixin,
    LifecycleAbleMixin,
    IDependentProvider[IdInputT, IdOutputT, AggInputT, AggOutputT],
    typing.Generic[IdInputT, IdOutputT, AggInputT, AggOutputT]
):
    """
    Provider for 1:M relationships (one parent to many children).

    Inverse of ReferenceProvider:
    - ReferenceProvider: For each child, finds/creates a parent (M:1)
    - DependentProvider: For one parent, creates N children (1:M)

    Uses IO2MDistributor to determine how many children to create.

    Example:
        class CompanyFaker(AggregateProvider):
            id: ValueProvider[int, int]
            name: ValueProvider[str, str]
            # 1:M - company has many employees
            employees: DependentProvider[int, int, dict, Employee]

            def __init__(self, repository, employee_provider, o2m_distributor):
                self.id = ValueProvider(...)
                self.name = ValueProvider(...)
                self.employees = DependentProvider(
                    distributor=o2m_distributor,  # determines count
                    aggregate_provider=employee_provider,  # template for children
                )
                super().__init__(repository=repository, ...)
    """

    _distributor: IO2MDistributor
    _aggregate_providers_accessor: IAggregateProvidersAccessor[AggInputT, AggOutputT, IdInputT, IdOutputT]
    _criteria: list[dict] | None = None
    _outputs: list[IdOutputT] | Empty = empty
    _count: int | None = None
    _weights: list[float] | None = None
    _value_selector: WeightedRangeDistributor | None = None
    _dependency_field: str | None = None
    _dependency_id: typing.Any = None

    def __init__(
            self,
            distributor: IO2MDistributor,
            aggregate_provider: (IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT] |
                                 Callable[[], IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]),
            dependency_field: str | None = None,
    ):
        """
        Args:
            distributor: O2M distributor that determines how many children to create
            aggregate_provider: Template provider for children (will be cloned for each child)
            dependency_field: Field name in child that references dependency's ID (FK field).
                          If set, this field will be automatically populated with dependency's ID.
        """
        super().__init__()
        self._distributor = distributor
        self._dependency_field = dependency_field
        self.aggregate_providers = aggregate_provider

    def _do_init(self):
        self._criteria = None
        self._outputs = empty
        self._count = None
        self._weights = None
        self._value_selector = None
        self._dependency_id = None
        self._on_required = SyncSignal[DependentCriteriaRequiredEvent]()
        self._on_populated = SyncSignal[InputPopulatedEvent]()
        super()._do_init()

    @property
    def on_required(self) -> ISyncSignal[DependentCriteriaRequiredEvent]:
        return self._on_required

    @property
    def on_populated(self) -> ISyncSignal[InputPopulatedEvent]:
        # DependentProvider doesn't use input signal, but interface requires it
        return self._on_populated

    def set_dependency_id(self, dependency_id: typing.Any) -> None:
        """Set dependency's ID to be used for related_field in dependents."""
        self._dependency_id = dependency_id

    async def create(self, session: ISession) -> list[IdOutputT]:
        """
        Returns list of IDs of created children.
        """
        if self._outputs is empty:
            return []

        results = []
        for provider in self.aggregate_providers:
            if provider._output is not empty:  # type: ignore[attr-defined]
                id_result = await provider.id_provider.create(session)
                results.append(id_result)
        return results

    async def populate(self, session: ISession) -> None:
        """
        Populate children providers.

        Uses distributor to determine count, then populates each child provider.

        If weights were provided via require(), uses WeightedRangeDistributor to select
        which value to use for each child (for creating hundreds of thousands of
        children from a small set of template values).
        """
        if self.is_complete():
            return

        # Determine count of children to create
        if self._count is None:
            # Ask distributor for count (weights mode uses distributor for count)
            self._count = self._distributor.distribute()

        # Get providers for the determined count
        providers = self.aggregate_providers

        # Set values on providers
        if self._criteria is not None:
            if self._value_selector is not None:
                # Weighted mode: select value for each child using WeightedRangeDistributor
                for provider in providers:
                    index = self._value_selector.distribute()
                    provider.require(self._criteria[index])
            else:
                # Direct mode: values[i] → child[i]
                for i, provider in enumerate(providers):
                    if i < len(self._criteria):
                        provider.require(self._criteria[i])

        # Set dependency's ID on dependency_field for each child (FK)
        if self._dependency_field is not None and self._dependency_id:
            for provider in providers:
                related_provider = getattr(provider, self._dependency_field, None)
                if related_provider is None:
                    raise AttributeError(
                        f"Provider '{self.provider_name}': child has no provider '{self._dependency_field}'"
                    )
                related_provider.require({'$eq': self._dependency_id})

        # Populate each provider
        for provider in providers:
            await provider.populate(session)

        # Collect results
        self._outputs = []
        for provider in providers:
            result = await provider.create(session)
            self._outputs.append(result)

    def require(self, criteria: list[dict], weights: list[float] | None = None) -> None:
        """
        Set input values for children.

        Args:
            criteria: List of criteria for children.
            weights: Optional list of weights for selecting values.
                     If not provided, each value corresponds to one child (direct mode).
                     If provided, WeightedRangeDistributor selects which value to use
                     for each child (weighted mode). Count is determined by distributor.

        Examples:
            # Direct mode: 3 children with specific values
            provider.require([{'name': 'A'}, {'name': 'B'}, {'name': 'C'}])

            # Weighted mode: N children (from distributor), 70% get value[0], 30% get value[1]
            provider.require(
                [{'department': 'IT'}, {'department': 'HR'}],
                weights=[0.7, 0.3]
            )
        """
        if self._criteria != criteria or self._weights != weights:
            self._criteria = criteria
            self._weights = weights
            self._outputs = empty

            if weights is not None:
                # Weighted mode: create selector, count from distributor
                self._value_selector = WeightedRangeDistributor(
                    min_val=0,
                    max_val=len(criteria) - 1,
                    weights=weights
                )
                self._count = None  # Will be determined by distributor
            else:
                # Direct mode: no selector, count from values
                self._value_selector = None
                self._count = len(criteria) if criteria else None

            self._on_required.notify(DependentCriteriaRequiredEvent(self._criteria, self._weights))

    def state(self) -> list[IdInputT]:
        """
        Get input values from all children providers.
        """
        if self._count is None or self._count == 0:
            return []
        return [provider.id_provider.state() for provider in self.aggregate_providers]

    def is_complete(self) -> bool:
        return self._outputs is not empty

    def is_transient(self) -> bool:
        return False

    async def append(self, session: ISession, value: IdOutputT):
        """Not used for O2M - children are created, not appended to distributor."""
        pass

    @property
    def aggregate_providers(self) -> list[IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]:
        """
        Returns list of aggregate providers for creating children.
        Count is determined by distributor or pre-set values.
        """
        count = self._count if self._count is not None else 0
        return self._aggregate_providers_accessor(count)

    @aggregate_providers.setter
    def aggregate_providers(
            self,
            aggregate_provider: (IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT] |
                                 Callable[[], IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]])
    ) -> None:
        """
        Sets the template aggregate provider.
        This provider will be cloned for each child.
        """
        # Check if it's a provider object (has 'clone' method) or a factory callable
        if hasattr(aggregate_provider, 'clone'):
            # It's already a provider object
            accessor = EagerAggregateProvidersAccessor[
                AggInputT, AggOutputT, IdInputT, IdOutputT
            ](aggregate_provider)
        else:
            # It's a factory callable
            accessor = LazyAggregateProvidersAccessor[
                AggInputT, AggOutputT, IdInputT, IdOutputT
            ](aggregate_provider)
        self._aggregate_providers_accessor = accessor

    def _do_clone(self, clone: typing.Self, shunt: ICloningShunt | None = None):
        clone._aggregate_providers_accessor = self._aggregate_providers_accessor.clone(shunt)
        super()._do_clone(clone, shunt)

    def _do_reset(self, visited: set) -> None:
        self._aggregate_providers_accessor.reset(visited)
        super()._do_reset(visited)

    async def setup(self, session: ISession):
        await self._aggregate_providers_accessor.setup(session)

    async def cleanup(self, session: ISession):
        await self._aggregate_providers_accessor.cleanup(session)


class EagerAggregateProvidersAccessor(
    IAggregateProvidersAccessor[AggInputT, AggOutputT, IdInputT, IdOutputT],
    typing.Generic[AggInputT, AggOutputT, IdInputT, IdOutputT]
):
    """
    Accessor that holds a direct reference to template provider.
    Clones the provider to create multiple children.
    """
    _template_provider: IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]
    _providers: list[IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]

    def __init__(
            self,
            template_provider: IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]
    ):
        self._template_provider = template_provider
        self._providers = []

    def __call__(self, count: int) -> list[IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]:
        # Extend list if needed by cloning template
        while len(self._providers) < count:
            cloned = self._template_provider.clone()
            self._providers.append(cloned)
        return self._providers[:count]

    def clone(self, shunt: ICloningShunt | None = None) -> typing.Self:
        return EagerAggregateProvidersAccessor[
            AggInputT, AggOutputT, IdInputT, IdOutputT
        ](self._template_provider.clone(shunt))

    def reset(self, visited: set | None = None):
        self._providers = []

    async def setup(self, session: ISession):
        await self._template_provider.setup(session)
        for provider in self._providers:
            await provider.setup(session)

    async def cleanup(self, session: ISession):
        await self._template_provider.cleanup(session)
        for provider in self._providers:
            await provider.cleanup(session)


class LazyAggregateProvidersAccessor(
    IAggregateProvidersAccessor[AggInputT, AggOutputT, IdInputT, IdOutputT],
    typing.Generic[AggInputT, AggOutputT, IdInputT, IdOutputT]
):
    """
    Accessor with lazy resolution of template provider.
    Useful for cyclic dependencies.
    """
    _template_provider: IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT] | None = None
    _template_provider_factory: Callable[[], IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]
    _providers: list[IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]

    def __init__(
            self,
            template_provider_factory: Callable[[], IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]
    ):
        self._template_provider_factory = template_provider_factory
        self._providers = []

    def _get_template(self) -> IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]:
        if self._template_provider is None:
            self._template_provider = self._template_provider_factory()
        return self._template_provider

    def __call__(self, count: int) -> list[IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]]:
        template = self._get_template()
        while len(self._providers) < count:
            cloned = template.clone()
            self._providers.append(cloned)
        return self._providers[:count]

    def clone(self, shunt: ICloningShunt | None = None) -> typing.Self:
        return LazyAggregateProvidersAccessor[
            AggInputT, AggOutputT, IdInputT, IdOutputT
        ](self._template_provider_factory)

    def reset(self, visited: set | None = None):
        self._template_provider = None
        self._providers = []

    async def setup(self, session: ISession):
        if self._template_provider is not None:
            await self._template_provider.setup(session)
        for provider in self._providers:
            await provider.setup(session)

    async def cleanup(self, session: ISession):
        if self._template_provider is not None:
            await self._template_provider.cleanup(session)
        for provider in self._providers:
            await provider.cleanup(session)
