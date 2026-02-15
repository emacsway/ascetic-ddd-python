import typing

from ascetic_ddd.kms.exceptions import KekNotFound
from ascetic_ddd.kms.interfaces import IKeyManagementService
from ascetic_ddd.kms.models import Kek, MasterKey, Algorithm
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.session.pg_session import extract_connection

__all__ = ("PgKeyManagementService",)


class PgKeyManagementService(IKeyManagementService):
    _extract_connection = staticmethod(extract_connection)

    _table = "kms_keys"

    _select_current_sql = """
        SELECT key_version, encrypted_key, master_algorithm, key_algorithm, created_at FROM %s
        WHERE tenant_id = %%s ORDER BY key_version DESC LIMIT 1
    """
    _select_version_sql = """
        SELECT encrypted_key, master_algorithm, key_algorithm, created_at FROM %s
        WHERE tenant_id = %%s AND key_version = %%s
    """
    _insert_sql = """
        INSERT INTO %s (tenant_id, key_version, encrypted_key, master_algorithm, key_algorithm)
        VALUES (%%s, %%s, %%s, %%s, %%s)
    """
    _delete_sql = "DELETE FROM %s WHERE tenant_id = %%s"

    _create_table_sql = """
        CREATE TABLE IF NOT EXISTS %s (
            tenant_id varchar(128) NOT NULL,
            key_version integer NOT NULL,
            encrypted_key bytea NOT NULL,
            master_algorithm varchar(32) NOT NULL,
            key_algorithm varchar(32) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT %s_pk PRIMARY KEY (tenant_id, key_version)
        )
    """

    def __init__(self, master_key: bytes, master_algorithm: Algorithm = Algorithm.AES_256_GCM) -> None:
        self._master_key = master_key
        self._master_algorithm = master_algorithm

    async def encrypt_dek(self, session: ISession, tenant_id: typing.Any, dek: bytes) -> bytes:
        kek = await self._get_or_create_current_kek(session, tenant_id)
        return kek.encrypt(dek)

    async def decrypt_dek(self, session: ISession, tenant_id: typing.Any, encrypted_dek: bytes) -> bytes:
        key_version = int.from_bytes(
            encrypted_dek[:Kek._KEY_VERSION_SIZE], "big"
        )
        kek = await self._get_kek(session, tenant_id, key_version)
        return kek.decrypt(encrypted_dek)

    async def generate_dek(self, session: ISession, tenant_id: typing.Any) -> tuple[bytes, bytes]:
        kek = await self._get_or_create_current_kek(session, tenant_id)
        return kek.generate_key()

    async def rotate_kek(self, session: ISession, tenant_id: typing.Any) -> int:
        master = self._make_master_key(tenant_id)
        try:
            kek = await self._get_current_kek(session, tenant_id)
            new_kek = master.rotate_obj(kek)
        except KekNotFound:
            new_kek = master.generate_obj(tenant_id=tenant_id)
        await self._save_kek(session, new_kek)
        return new_kek.version

    async def rewrap_dek(self, session: ISession, tenant_id: typing.Any, encrypted_dek: bytes) -> bytes:
        dek = await self.decrypt_dek(session, tenant_id, encrypted_dek)
        return await self.encrypt_dek(session, tenant_id, dek)

    async def delete_kek(self, session: ISession, tenant_id: typing.Any) -> None:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._delete_sql % self._table, [tenant_id])

    def _make_master_key(self, tenant_id: typing.Any, algorithm: Algorithm | None = None) -> MasterKey:
        return MasterKey(
            tenant_id=tenant_id,
            key=self._master_key,
            algorithm=algorithm or self._master_algorithm,
        )

    async def _get_or_create_current_kek(self, session: ISession, tenant_id: typing.Any) -> Kek:
        try:
            return await self._get_current_kek(session, tenant_id)
        except KekNotFound:
            await self.rotate_kek(session, tenant_id)
            return await self._get_current_kek(session, tenant_id)

    async def _get_current_kek(self, session: ISession, tenant_id: typing.Any) -> Kek:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._select_current_sql % self._table, [tenant_id])
            row = await acursor.fetchone()
        if row is None:
            raise KekNotFound(tenant_id)
        key_version, encrypted_key, master_algorithm, key_algorithm, created_at = row
        master = self._make_master_key(tenant_id, Algorithm(master_algorithm))
        return master.load_obj(
            tenant_id=tenant_id,
            encrypted_key=bytes(encrypted_key),
            version=key_version,
            algorithm=Algorithm(key_algorithm),
            created_at=created_at,
        )

    async def _get_kek(self, session: ISession, tenant_id: typing.Any, key_version: int) -> Kek:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._select_version_sql % self._table, [tenant_id, key_version])
            row = await acursor.fetchone()
        if row is None:
            raise KekNotFound(tenant_id, key_version)
        encrypted_key, master_algorithm, key_algorithm, created_at = row
        master = self._make_master_key(tenant_id, Algorithm(master_algorithm))
        return master.load_obj(
            tenant_id=tenant_id,
            encrypted_key=bytes(encrypted_key),
            version=key_version,
            algorithm=Algorithm(key_algorithm),
            created_at=created_at,
        )

    async def _save_kek(self, session: ISession, kek: Kek) -> None:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._insert_sql % self._table, [
                kek.tenant_id, kek.version, kek.encrypted_key,
                self._master_algorithm.value, kek.algorithm.value,
            ])

    async def setup(self, session: ISession) -> None:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(
                self._create_table_sql % (self._table, self._table)
            )

    async def cleanup(self, session: ISession) -> None:
        pass
