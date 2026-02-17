import typing
import dataclasses

from ascetic_ddd.session.interfaces import ISession

T = typing.TypeVar("T")


# --- Distributor events ---

@dataclasses.dataclass(frozen=True)
class ValueAppendedEvent(typing.Generic[T]):
    session: ISession
    value: T
    position: int | None
