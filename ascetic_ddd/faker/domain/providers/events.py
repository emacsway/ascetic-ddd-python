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
class DependentCriteriaRequiredEvent:
    criteria: list[dict]
    weights: list[float] | None = None


@dataclasses.dataclass(frozen=True)
class OutputPopulatedEvent(typing.Generic[T]):
    output: T
