import typing
import dataclasses

from ascetic_ddd.faker.domain.query.operators import IQueryOperator
from ascetic_ddd.session.interfaces import ISession

T = typing.TypeVar("T")


# --- Repository events ---

@dataclasses.dataclass(frozen=True)
class AggregateInsertedEvent(typing.Generic[T]):
    session: ISession
    agg: T


@dataclasses.dataclass(frozen=True)
class AggregateUpdatedEvent(typing.Generic[T]):
    session: ISession
    agg: T


# --- Provider events ---

@dataclasses.dataclass(frozen=True)
class CriteriaRequiredEvent:
    criteria: IQueryOperator


@dataclasses.dataclass(frozen=True)
class InputSetEvent(typing.Generic[T]):
    input: T
