import typing
from abc import ABCMeta

from ascetic_ddd.seedwork.domain.aggregate.interfaces import IEventiveEntity

__all__ = ("EventiveEntity",)

DomainEventT_co = typing.TypeVar("DomainEventT_co", covariant=True)


class EventiveEntity(typing.Generic[DomainEventT_co], IEventiveEntity[DomainEventT_co], metaclass=ABCMeta):
    def __init__(self, **kwargs) -> None:
        self.__pending_domain_events = []
        super().__init__(**kwargs)

    def _add_domain_event(self, event: DomainEventT_co) -> None:
        self.__pending_domain_events.append(event)

    @property
    def pending_domain_events(self) -> typing.Iterable[DomainEventT_co]:
        return tuple(self.__pending_domain_events)

    @pending_domain_events.deleter
    def pending_domain_events(self) -> None:
        self.__pending_domain_events.clear()
