import typing
from abc import ABCMeta, abstractmethod
from collections.abc import Callable, Hashable

from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.seedwork.domain.identity.interfaces import IAccessible
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.signals.interfaces import ISyncSignal, IAsyncSignal
from ascetic_ddd.faker.domain.providers.events import (
    CriteriaRequiredEvent,
    InputPopulatedEvent,
    AggregateInsertedEvent,
    AggregateUpdatedEvent,
)

__all__ = (
    'INameable',
    'ICloningShunt',
    'ILifecycleAble',
    'ISetupable',
    'IProvidable',
    'IInputOutput',
    'IValueProvider',
    'IRelativeValueProvider',
    'ICompositeValueProvider',
    'IEntityProvider',
    'IAggregateRepository',
    'IAggregateProvider',
    'IReferenceProvider',
    'IDependentInputOutput',
    'IDependentProvider',
)

InputT = typing.TypeVar("InputT")
OutputT = typing.TypeVar("OutputT")
CloneableT = typing.TypeVar("CloneableT")
AggProviderT = typing.TypeVar("AggProviderT")


class INameable(metaclass=ABCMeta):

    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @provider_name.setter
    @abstractmethod
    def provider_name(self, value: str):
        raise NotImplementedError


class ICloningShunt(metaclass=ABCMeta):

    @abstractmethod
    def __getitem__(self, key: typing.Hashable) -> typing.Any:
        raise NotImplementedError

    @abstractmethod
    def __setitem__(self, key: typing.Hashable, value: typing.Any):
        raise NotImplementedError

    @abstractmethod
    def __contains__(self, key: typing.Hashable):
        raise NotImplementedError


class ILifecycleAble(metaclass=ABCMeta):

    @abstractmethod
    def reset(self, visited: set | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def clone(self, shunt: ICloningShunt | None = None) -> typing.Self:
        # For older python: def clone(self: CloneableT, shunt: IShunt | None = None) -> CloneableT:
        raise NotImplementedError


class ISetupable(metaclass=ABCMeta):

    @abstractmethod
    async def setup(self, session: ISession):
        raise NotImplementedError

    @abstractmethod
    async def cleanup(self, session: ISession):
        raise NotImplementedError


class IProvidable(metaclass=ABCMeta):

    @abstractmethod
    async def populate(self, session: ISession) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_complete(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_transient(self) -> bool:
        raise NotImplementedError


class IInputOutput(typing.Generic[InputT, OutputT], metaclass=ABCMeta):
    @abstractmethod
    async def create(self, session: ISession) -> OutputT:
        raise NotImplementedError

    @abstractmethod
    def require(self, criteria: dict[str, typing.Any]) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def on_required(self) -> ISyncSignal[CriteriaRequiredEvent]:
        raise NotImplementedError

    @property
    @abstractmethod
    def on_populated(self) -> ISyncSignal[InputPopulatedEvent[InputT]]:
        raise NotImplementedError

    @abstractmethod
    def state(self) -> InputT:
        raise NotImplementedError

    @abstractmethod
    async def append(self, session: ISession, value: OutputT):
        raise NotImplementedError


class IValueProvider(
    IInputOutput[InputT, OutputT], IProvidable, INameable, ILifecycleAble,
    ISetupable, typing.Generic[InputT, OutputT], metaclass=ABCMeta
):
    pass


class IRelativeValueProvider(IValueProvider[InputT, OutputT], typing.Generic[InputT, OutputT], metaclass=ABCMeta):

    @abstractmethod
    def set_scope(self, scope: Hashable) -> None:
        raise NotImplementedError


class ICompositeValueProvider(
    IValueProvider[InputT, OutputT], typing.Generic[InputT, OutputT], metaclass=ABCMeta
):
    @property
    @abstractmethod
    def providers(self) -> dict[str, IValueProvider[typing.Any, typing.Any]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def dependent_providers(self) -> dict[str, 'IDependentProvider[typing.Any, typing.Any, typing.Any]']:
        raise NotImplementedError


class IEntityProvider(
    ICompositeValueProvider[InputT, OutputT], typing.Generic[InputT, OutputT], metaclass=ABCMeta
):

    @property
    @abstractmethod
    def id_provider(self) -> IValueProvider[InputT, OutputT]:
        raise NotImplementedError


class IAggregateRepository(typing.Protocol[OutputT]):

    @property
    def on_inserted(self) -> IAsyncSignal[AggregateInsertedEvent[OutputT]]:
        ...

    @property
    def on_updated(self) -> IAsyncSignal[AggregateUpdatedEvent[OutputT]]:
        ...

    async def insert(self, session: ISession, agg: OutputT):
        ...

    async def get(self, session: ISession, id_: IAccessible[typing.Any]) -> OutputT | None:
        ...

    async def update(self, session: ISession, agg: OutputT):
        ...

    async def find(self, session: ISession, specification: ISpecification) -> typing.Iterable[OutputT]:
        ...

    async def setup(self, session: ISession):
        ...

    async def cleanup(self, session: ISession):
        ...


class IAggregateProvider(
    IEntityProvider[InputT, OutputT], typing.Generic[InputT, OutputT], metaclass=ABCMeta
):
    # TODO: move id_provider here?

    @property
    @abstractmethod
    def repository(self) -> IAggregateRepository[OutputT]:
        raise NotImplementedError


class IReferenceProvider(
    IValueProvider[InputT, OutputT],
    typing.Generic[InputT, OutputT, AggProviderT], metaclass=ABCMeta
):

    @property
    @abstractmethod
    def aggregate_provider(self) -> IAggregateProvider[InputT, AggProviderT]:
        raise NotImplementedError

    @aggregate_provider.setter
    @abstractmethod
    def aggregate_provider(
            self,
            aggregate_provider: IAggregateProvider[InputT, AggProviderT] | Callable[[], IAggregateProvider[InputT, AggProviderT]]
    ) -> None:
        raise NotImplementedError


class IDependentInputOutput(typing.Generic[InputT, OutputT], metaclass=ABCMeta):

    @abstractmethod
    async def create(self, session: ISession) -> list[OutputT]:
        raise NotImplementedError

    @abstractmethod
    def require(self, criteria: list[dict], weights: list[float] | None = None) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def on_required(self) -> ISyncSignal[CriteriaRequiredEvent]:
        raise NotImplementedError

    @property
    @abstractmethod
    def on_populated(self) -> ISyncSignal[InputPopulatedEvent[list[InputT]]]:
        raise NotImplementedError

    @abstractmethod
    def state(self) -> list[InputT]:
        raise NotImplementedError


class IDependentProvider(
    IDependentInputOutput[InputT, OutputT], IProvidable, INameable, ILifecycleAble,
    ISetupable, typing.Generic[InputT, OutputT, AggProviderT], metaclass=ABCMeta
):

    @property
    @abstractmethod
    def aggregate_providers(self) -> list[IAggregateProvider[InputT, AggProviderT]]:
        raise NotImplementedError

    @aggregate_providers.setter
    @abstractmethod
    def aggregate_providers(
            self,
            aggregate_provider: list[IAggregateProvider[InputT, AggProviderT] |
                                     Callable[[], IAggregateProvider[InputT, AggProviderT]]]
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_dependency_id(self, dependency_id: typing.Any) -> None:
        raise NotImplementedError
