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
        # Reflection could also be used here.
        # But I chose the classical approach here for three reasons:
        #
        # 1. "programming in a language vs. programming into a language" -- Steve McConnell, Code Complete 2nd ed.
        # It is better to follow practices independent of a specific programming language -- this will make it
        # easier to port the code to a more performant statically typed language.
        #
        # 2. Greg Young's recommendation:
        # This table represents the actual Event Log. There will be one entry per event in this table.
        # The event itself is stored in the [Data] column.
        # The event is stored using some form of serialization, for the rest of this discussion the mechanism
        # will assumed to be built in serialization although the use of the memento pattern can be highly advantageous.
        # -- "`CQRS Documents by Greg Young <https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf>`__"
        #
        # 3. This is not that bad, since keyboard typing does not significantly affect the development velocity,
        # as it takes no more than 10% of the code construction time.
        # At the same time, the probability of an error is also minimal,
        # since it is easily caught by a static code analyzer.
        #
        # In the future, all code will be generated from EventStorming diagrams and code generation will be used,
        # see the "Metadata Mapping" chapter of "Patterns of Enterprise Application Architecture" by Martin Fowler
        #
        # See also:
        # https://dckms.github.io/system-architecture/emacsway/it/ddd/grade/domain/shotgun-surgery.html

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
    def set_event_meta(self, meta: EventMeta) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_aggregate_version(self, value: int) -> None:
        raise NotImplementedError
