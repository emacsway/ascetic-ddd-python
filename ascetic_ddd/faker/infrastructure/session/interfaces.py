import typing
from abc import abstractmethod

from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.session.interfaces import IAsyncConnection


__all__ = (
    "IExternalPgSession",
    "IInternalPgSession",
)


@typing.runtime_checkable
class IExternalPgSession(ISession, typing.Protocol):

    @property
    @abstractmethod
    def external_connection(self) -> IAsyncConnection:
        """For ReadModels (Queries)."""
        ...


@typing.runtime_checkable
class IInternalPgSession(ISession, typing.Protocol):

    @property
    @abstractmethod
    def internal_connection(self) -> IAsyncConnection:
        """For ReadModels (Queries)."""
        ...


class IAuthenticator(typing.Protocol):

    async def authenticate(self, session: ISession):
        ...
