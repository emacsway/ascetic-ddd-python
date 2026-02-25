import typing

from ascetic_ddd.faker.infrastructure.session import IInternalPgSession, IExternalPgSession
from ascetic_ddd.session.interfaces import IAsyncConnection, ISession
from ascetic_ddd.session.identity_map import IdentityMap
from ascetic_ddd.session.pg_session import PgSession, PgSessionPool, PgAtomicSession, extract_connection

__all__ = (
    'extract_internal_connection',
    'extract_external_connection',
    'InternalPgSessionPool',
    'InternalPgSession',
    'InternalPgAtomicSession',
    'ExternalPgSessionPool',
    'ExternalPgSession',
    'ExternalPgAtomicSession',
)


def extract_internal_connection(session: ISession) -> IAsyncConnection[tuple[typing.Any, ...]]:
    try:
        return typing.cast(IInternalPgSession, session).internal_connection
    except AttributeError:
        return extract_connection(session)


def extract_external_connection(session: ISession) -> IAsyncConnection[tuple[typing.Any, ...]]:
    try:
        return typing.cast(IExternalPgSession, session).external_connection
    except AttributeError:
        return extract_connection(session)


class InternalPgSessionPool(PgSessionPool):
    @staticmethod
    def _make_session(connection):
        return InternalPgSession(connection, IdentityMap(isolation_level=IdentityMap.READ_UNCOMMITTED))


class InternalPgSession(PgSession):
    internal_connection = PgSession.connection

    def _make_atomic_session(self, connection):
        return InternalPgAtomicSession(connection, IdentityMap(), self)


class InternalPgAtomicSession(PgAtomicSession):
    internal_connection = PgSession.connection

    def _make_atomic_session(self, connection):
        return InternalPgAtomicSession(connection, self._identity_map, self)


class ExternalPgSessionPool(PgSessionPool):
    @staticmethod
    def _make_session(connection):
        return ExternalPgSession(connection, IdentityMap(isolation_level=IdentityMap.READ_UNCOMMITTED))


class ExternalPgSession(PgSession):
    external_connection = PgSession.connection

    def _make_atomic_session(self, connection):
        return ExternalPgAtomicSession(connection, IdentityMap(), self)


class ExternalPgAtomicSession(PgAtomicSession):
    external_connection = PgSession.connection

    def _make_atomic_session(self, connection):
        return ExternalPgAtomicSession(connection, self._identity_map, self)
