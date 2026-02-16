import typing
from abc import ABCMeta

from ascetic_ddd.seedwork.domain.aggregate.interfaces import IEventiveEntity

__all__ = ("EventiveEntity",)

DomainEventT = typing.TypeVar("DomainEventT")


class EventiveEntity(IEventiveEntity[DomainEventT], typing.Generic[DomainEventT], metaclass=ABCMeta):
    def __init__(self, **kwargs) -> None:
        self.__pending_domain_events = []
        super().__init__(**kwargs)

    def _add_domain_event(self, event: DomainEventT) -> None:
        self.__pending_domain_events.append(event)

    @property
    def pending_domain_events(self) -> typing.Iterable[DomainEventT]:
        return tuple(self.__pending_domain_events)

    @pending_domain_events.deleter
    def pending_domain_events(self) -> None:
        self.__pending_domain_events.clear()
