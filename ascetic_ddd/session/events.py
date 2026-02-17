from __future__ import annotations

import typing
import dataclasses

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ascetic_ddd.session.interfaces import ISession


__all__ = (
    'SessionScopeStartedEvent',
    'SessionScopeEndedEvent',
    'QueryStartedEvent',
    'QueryEndedEvent',
    'RequestStartedEvent',
    'RequestEndedEvent',
)


# --- Session events ---


@dataclasses.dataclass(frozen=True)
class SessionScopeStartedEvent:
    session: ISession


@dataclasses.dataclass(frozen=True)
class SessionScopeEndedEvent:
    session: ISession


@dataclasses.dataclass(frozen=True)
class QueryStartedEvent:
    query: typing.Any
    params: typing.Any
    sender: typing.Any
    session: typing.Any  # weakref


@dataclasses.dataclass(frozen=True)
class QueryEndedEvent:
    query: typing.Any
    params: typing.Any
    sender: typing.Any
    session: typing.Any  # weakref
    response_time: float


@dataclasses.dataclass(frozen=True)
class RequestStartedEvent:
    session: ISession
    sender: typing.Any
    request_view: typing.Any


@dataclasses.dataclass(frozen=True)
class RequestEndedEvent:
    session: ISession
    sender: typing.Any
    request_view: typing.Any
