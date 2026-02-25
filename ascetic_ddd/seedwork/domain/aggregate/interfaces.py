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


DomainEventT = typing.TypeVar("DomainEventT")


class IDomainEventAdder(typing.Generic[DomainEventT], metaclass=ABCMeta):
    @abstractmethod
    def _add_domain_event(self, event: DomainEventT):
        raise NotImplementedError


class IDomainEventAccessor(typing.Generic[DomainEventT], metaclass=ABCMeta):
    @property
    @abstractmethod
    def pending_domain_events(self) -> typing.Iterable[DomainEventT]:
        raise NotImplementedError

    @pending_domain_events.deleter
    @abstractmethod
    def pending_domain_events(self) -> None:
        raise NotImplementedError


class IEventiveEntity(
    IDomainEventAdder[DomainEventT],
    IDomainEventAccessor[DomainEventT],
    typing.Generic[DomainEventT],
    metaclass=ABCMeta
):
    pass


PersistentDomainEventT = typing.TypeVar("PersistentDomainEventT")


class IDomainEventLoader(typing.Generic[PersistentDomainEventT], metaclass=ABCMeta):

    @classmethod
    def fold(cls, past_events: typing.Iterable[PersistentDomainEventT]):
        """
        Or reduce.
        """
        raise NotImplementedError


class IEventSourcedAggregate(
    typing.Generic[PersistentDomainEventT],
    IDomainEventLoader[PersistentDomainEventT],
    IEventiveEntity[PersistentDomainEventT],
    IVersionedAggregate,
    metaclass=ABCMeta,
):
    @abstractmethod
    def _update(self, e: PersistentDomainEventT) -> None:
        raise NotImplementedError
