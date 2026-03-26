import typing
from abc import ABCMeta, abstractmethod
from collections.abc import Callable, Hashable

from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.seedwork.domain.identity.interfaces import IAccessible
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.signals.interfaces import ISyncSignal, IAsyncSignal
from ascetic_ddd.faker.domain.providers.events import (
    CriteriaRequiredEvent,
    DependentCriteriaRequiredEvent,
    OutputPopulatedEvent,
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
CompositeInputT = typing.TypeVar("CompositeInputT", bound=dict)
CompositeOutputT = typing.TypeVar("CompositeOutputT", bound=object)
CloneableT = typing.TypeVar("CloneableT")

IdInputT = typing.TypeVar("IdInputT")
IdOutputT = typing.TypeVar("IdOutputT")
AggInputT = typing.TypeVar("AggInputT", bound=dict)
AggOutputT = typing.TypeVar("AggOutputT", bound=object)


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
    def output(self) -> OutputT:
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
    def on_populated(self) -> IAsyncSignal[OutputPopulatedEvent[OutputT]]:
        raise NotImplementedError

    @abstractmethod
    def state(self) -> InputT:
        raise NotImplementedError

    @abstractmethod
    def export(self, output: OutputT) -> InputT:
        raise NotImplementedError

    @abstractmethod
    async def append(self, session: ISession, value: OutputT):
        raise NotImplementedError


class IValueProvider(
    IInputOutput[InputT, OutputT], IProvidable, INameable, ILifecycleAble,
    ISetupable, typing.Generic[InputT, OutputT], metaclass=ABCMeta
):
    pass


class ICompositeValueProvider(
    IValueProvider[CompositeInputT, CompositeOutputT],
    typing.Generic[CompositeInputT, CompositeOutputT],
    metaclass=ABCMeta
):
    @property
    @abstractmethod
    def providers(self) -> dict[str, IValueProvider[typing.Any, typing.Any]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def dependent_providers(self) -> dict[str, 'IDependentProvider[typing.Any, typing.Any, typing.Any, typing.Any]']:
        raise NotImplementedError


class IEntityProvider(
    ICompositeValueProvider[AggInputT, AggOutputT],
    typing.Generic[AggInputT, AggOutputT, IdInputT, IdOutputT],
    metaclass=ABCMeta
):

    @property
    @abstractmethod
    def id_provider(self) -> IValueProvider[IdInputT, IdOutputT]:
        raise NotImplementedError


class IAggregateRepository(typing.Protocol[AggOutputT]):

    @property
    def table(self) -> str:
        ...

    @property
    def on_inserted(self) -> IAsyncSignal[AggregateInsertedEvent[AggOutputT]]:
        ...

    @property
    def on_updated(self) -> IAsyncSignal[AggregateUpdatedEvent[AggOutputT]]:
        ...

    async def insert(self, session: ISession, agg: AggOutputT):
        ...

    async def get(self, session: ISession, id_: IAccessible[typing.Any]) -> AggOutputT | None:
        ...

    async def update(self, session: ISession, agg: AggOutputT):
        ...

    async def find(self, session: ISession, specification: ISpecification) -> typing.Iterable[AggOutputT]:
        ...

    async def setup(self, session: ISession):
        ...

    async def cleanup(self, session: ISession):
        ...


class IAggregateProvider(
    IEntityProvider[AggInputT, AggOutputT, IdInputT, IdOutputT],
    typing.Generic[AggInputT, AggOutputT, IdInputT, IdOutputT],
    metaclass=ABCMeta
):
    # TODO: move id_provider here?

    @property
    @abstractmethod
    def repository(self) -> IAggregateRepository[AggOutputT]:
        raise NotImplementedError


class IReferenceProvider(
    IValueProvider[IdInputT, IdOutputT],
    typing.Generic[IdInputT, IdOutputT, AggInputT, AggOutputT], metaclass=ABCMeta
):

    @property
    @abstractmethod
    def aggregate_provider(self) -> IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]:
        raise NotImplementedError

    @aggregate_provider.setter
    @abstractmethod
    def aggregate_provider(
            self,
            aggregate_provider: (IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT] |
                                 Callable[[], IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]])
    ) -> None:
        raise NotImplementedError


class IDependentInputOutput(typing.Generic[InputT, OutputT], metaclass=ABCMeta):

    @abstractmethod
    def create(self) -> list[OutputT]:
        raise NotImplementedError

    @abstractmethod
    def require(self, criteria: list[dict], weights: list[float] | None = None) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def on_required(self) -> ISyncSignal[DependentCriteriaRequiredEvent]:
        raise NotImplementedError

    @property
    @abstractmethod
    def on_populated(self) -> IAsyncSignal[OutputPopulatedEvent[list[OutputT]]]:
        raise NotImplementedError

    @abstractmethod
    def state(self) -> list[InputT]:
        raise NotImplementedError

    @abstractmethod
    def export(self, output: OutputT) -> InputT:
        raise NotImplementedError


class IDependentProvider(
    IDependentInputOutput[IdInputT, IdOutputT],
    IProvidable,
    INameable,
    ILifecycleAble,
    ISetupable,
    typing.Generic[IdInputT, IdOutputT, AggInputT, AggOutputT],
    metaclass=ABCMeta
):

    @property
    @abstractmethod
    def aggregate_providers(self) -> list[
        IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]
    ]:
        raise NotImplementedError

    @aggregate_providers.setter
    @abstractmethod
    def aggregate_providers(
            self,
            aggregate_provider: (IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT] |
                                 Callable[[], IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT]])
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_dependency_id(self, dependency_id: IdInputT) -> None:
        raise NotImplementedError
