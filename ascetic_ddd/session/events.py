from __future__ import annotations

import typing
import dataclasses

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ascetic_ddd.session.interfaces import ISession, IPgSession, Query, Params


__all__ = (
    'SessionScopeStartedEvent',
    'SessionScopeEndedEvent',
    'QueryStartedEvent',
    'QueryEndedEvent',
    'RequestViewModel',
    'RequestStartedEvent',
    'RequestEndedEvent',
)


@dataclasses.dataclass(frozen=True)
class SessionScopeStartedEvent:
    session: ISession


@dataclasses.dataclass(frozen=True)
class SessionScopeEndedEvent:
    session: ISession


@dataclasses.dataclass(frozen=True)
class QueryStartedEvent:
    query: Query
    params: Params | None
    sender: typing.Any
    session: IPgSession


@dataclasses.dataclass(frozen=True)
class QueryEndedEvent:
    query: Query
    params: Params | None
    sender: typing.Any
    session: IPgSession
    response_time: float


@dataclasses.dataclass(kw_only=True)
class RequestViewModel:
    time_start: float
    label: str
    status: int | None
    response_time: float | None

    def __str__(self):
        return self.label + "." + str(self.status)


@dataclasses.dataclass(frozen=True)
class RequestStartedEvent:
    session: ISession
    sender: typing.Any
    request_view: RequestViewModel


@dataclasses.dataclass(frozen=True)
class RequestEndedEvent:
    session: ISession
    sender: typing.Any
    request_view: RequestViewModel
