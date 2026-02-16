import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.specification.domain.interfaces import IEqualOperand

__all__ = (
    "IVersionedAggregate",
    "IDomainEventAdder",
    "IDomainEventAccessor",
    "IEventiveEntity",
    "IDomainEventLoader",
    "IEventSourcedAggregate",
    "IHashable",
)


class IVersionedAggregate(metaclass=ABCMeta):
    @property
    @abstractmethod
    def version(self) -> int:
        raise NotImplementedError

    @version.setter
    @abstractmethod
    def version(self, value: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def next_version(self) -> int:
        raise NotImplementedError


DomainEventT_co = typing.TypeVar("DomainEventT_co", covariant=True)


class IDomainEventAdder(typing.Generic[DomainEventT_co], metaclass=ABCMeta):
    @abstractmethod
    def _add_domain_event(self, event: DomainEventT_co):
        raise NotImplementedError


class IDomainEventAccessor(typing.Generic[DomainEventT_co], metaclass=ABCMeta):
    @property
    @abstractmethod
    def pending_domain_events(self) -> typing.Iterable[DomainEventT_co]:
        raise NotImplementedError

    @pending_domain_events.deleter
    @abstractmethod
    def pending_domain_events(self) -> None:
        raise NotImplementedError


class IEventiveEntity(
    typing.Generic[DomainEventT_co], IDomainEventAdder[DomainEventT_co], IDomainEventAccessor[DomainEventT_co], metaclass=ABCMeta
):
    pass


PersistentDomainEventT_co = typing.TypeVar("PersistentDomainEventT_co", covariant=True)


class IDomainEventLoader(typing.Generic[PersistentDomainEventT_co], metaclass=ABCMeta):
    @abstractmethod
    def _load_from(self, past_events: typing.Iterable[PersistentDomainEventT_co]) -> None:
        raise NotImplementedError


class IEventSourcedAggregate(
    typing.Generic[PersistentDomainEventT_co],
    IDomainEventLoader[IDomainEventLoader],
    IEventiveEntity[PersistentDomainEventT_co],
    IVersionedAggregate,
    metaclass=ABCMeta,
):
    @abstractmethod
    def _update(self, e: PersistentDomainEventT_co) -> None:
        raise NotImplementedError


class IHashable(IEqualOperand, typing.Protocol):

    def __hash__(self) -> int:
        ...
