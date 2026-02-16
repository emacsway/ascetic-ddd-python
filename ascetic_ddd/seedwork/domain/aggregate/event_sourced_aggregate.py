import dataclasses
import typing
from abc import ABCMeta

from ascetic_ddd.seedwork.domain.aggregate.eventive_entity import EventiveEntity
from ascetic_ddd.seedwork.domain.aggregate.interfaces import IEventSourcedAggregate
from ascetic_ddd.seedwork.domain.aggregate.versioned_aggregate import VersionedAggregate

__all__ = ("EventSourcedAggregate",)

PersistentDomainEventT = typing.TypeVar("PersistentDomainEventT")


class EventSourcedAggregate(
    EventiveEntity[PersistentDomainEventT],
    VersionedAggregate,
    IEventSourcedAggregate[PersistentDomainEventT],
    typing.Generic[PersistentDomainEventT],
    metaclass=ABCMeta,
):
    class Handlers(dict):
        def register(self, event_type: type[PersistentDomainEventT]):
            def do_register(handler: typing.Callable[["EventSourcedAggregate", PersistentDomainEventT], None]):
                self[event_type] = handler
                return handler

            return do_register

    _handlers = Handlers()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def _load_from(self, past_events: typing.Iterable[PersistentDomainEventT]) -> None:
        for event in past_events:
            self.version = event.aggregate_version
            self._handlers[type(event)](self, event)

    def _update(self, event: PersistentDomainEventT) -> None:
        event = dataclasses.replace(event, aggregate_version=self.next_version())
        self._add_domain_event(event)
        self._handlers[type(event)](self, event)

    @classmethod
    def fold(cls, past_events: typing.Iterable[PersistentDomainEventT]):
        """
        Or reduce.
        """
        agg: typing.Self = cls.make_empty()
        agg._load_from(past_events)
        return agg
