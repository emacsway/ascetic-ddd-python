import typing

from ascetic_ddd.seedwork.domain.aggregate.event_meta import EventMeta
from ascetic_ddd.seedwork.domain.aggregate.event_meta_exporter import EventMetaExporter
from ascetic_ddd.seedwork.domain.aggregate.persistent_domain_event import IPersistentDomainEventExporter

__all__ = ("PersistentDomainEventExporter",)


class PersistentDomainEventExporter(IPersistentDomainEventExporter):
    data: dict[str, typing.Any]

    def __init__(self) -> None:
        self.data = {}

    def set_event_type(self, value: str) -> None:
        self.data["event_type"] = value

    def set_event_version(self, value: int) -> None:
        self.data["event_version"] = value

    def set_event_meta(self, meta: EventMeta | None) -> None:
        if meta is None:
            return
        exporter = EventMetaExporter()
        meta.export(exporter)
        self.data["event_meta"] = exporter.data

    def set_aggregate_version(self, value: int) -> None:
        self.data["aggregate_version"] = value
