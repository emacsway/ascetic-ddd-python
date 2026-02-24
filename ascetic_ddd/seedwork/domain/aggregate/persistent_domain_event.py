from abc import ABCMeta, abstractmethod
from dataclasses import dataclass

from ascetic_ddd.seedwork.domain.aggregate.domain_event import DomainEvent
from ascetic_ddd.seedwork.domain.aggregate.event_meta import EventMeta

__all__ = (
    "PersistentDomainEvent",
    "IPersistentDomainEventExporter",
)


@dataclass(frozen=True, kw_only=True)
class PersistentDomainEvent(DomainEvent):
    event_version: int = 1
    event_meta: EventMeta | None = None
    aggregate_version: int = 0
    # occurred_at: datetime.datetime = None  # for partitioning?
    # Where would this value be known at the domain level? Let it remain in Meta.

    @property
    def event_type(self):
        return type(self).__name__

    def export(self, exporter: "IPersistentDomainEventExporter") -> None:
        exporter.set_event_type(self.event_type)
        exporter.set_event_version(self.event_version)
        exporter.set_event_meta(self.event_meta)
        exporter.set_aggregate_version(self.aggregate_version)


class IPersistentDomainEventExporter(metaclass=ABCMeta):

    @abstractmethod
    def set_event_type(self, value: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_event_version(self, value: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_event_meta(self, meta: EventMeta | None) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_aggregate_version(self, value: int) -> None:
        raise NotImplementedError
