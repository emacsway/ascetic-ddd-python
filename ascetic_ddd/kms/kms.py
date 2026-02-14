import os
import typing

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ascetic_ddd.kms.interfaces import IKeyManagementService
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.session.pg_session import extract_connection

__all__ = ("PgKeyManagementService",)


class PgKeyManagementService(IKeyManagementService):
    _extract_connection = staticmethod(extract_connection)
    _NONCE_SIZE = 12
    _KEY_VERSION_SIZE = 4

    _select_current_sql = """
        SELECT key_version, encrypted_kek FROM kms_keys
        WHERE tenant_id = %s ORDER BY key_version DESC LIMIT 1
    """
    _select_version_sql = """
        SELECT encrypted_kek FROM kms_keys
        WHERE tenant_id = %s AND key_version = %s
    """
    _insert_sql = """
        INSERT INTO kms_keys (tenant_id, key_version, encrypted_kek)
        VALUES (%s, %s, %s)
    """
    _delete_sql = "DELETE FROM kms_keys WHERE tenant_id = %s"
    _table = "kms_keys"

    _create_table_sql = """
        CREATE TABLE IF NOT EXISTS %s (
            tenant_id varchar(128) NOT NULL,
            key_version integer NOT NULL,
            encrypted_kek bytea NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT %s_pk PRIMARY KEY (tenant_id, key_version)
        )
    """

    def __init__(self, master_key: bytes) -> None:
        self._aesgcm = AESGCM(master_key)

    async def encrypt_dek(self, session: ISession, tenant_id: typing.Any, dek: bytes) -> bytes:
        try:
            key_version, kek = await self._get_current_kek(session, tenant_id)
        except KeyError:
            _ = await self.rotate_kek(session, tenant_id)
            key_version, kek = await self._get_current_kek(session, tenant_id)
        kek_aesgcm = AESGCM(kek)
        nonce = os.urandom(self._NONCE_SIZE)
        version_bytes = key_version.to_bytes(self._KEY_VERSION_SIZE, "big")
        return version_bytes + nonce + kek_aesgcm.encrypt(nonce, dek, None)

    async def decrypt_dek(self, session: ISession, tenant_id: typing.Any, encrypted_dek: bytes) -> bytes:
        key_version = int.from_bytes(
            encrypted_dek[:self._KEY_VERSION_SIZE], "big"
        )
        kek = await self._get_kek(session, tenant_id, key_version)
        kek_aesgcm = AESGCM(kek)
        nonce = encrypted_dek[self._KEY_VERSION_SIZE:self._KEY_VERSION_SIZE + self._NONCE_SIZE]
        ciphertext = encrypted_dek[self._KEY_VERSION_SIZE + self._NONCE_SIZE:]
        return kek_aesgcm.decrypt(nonce, ciphertext, None)

    async def generate_dek(self, session: ISession, tenant_id: typing.Any) -> tuple[bytes, bytes]:
        dek = AESGCM.generate_key(bit_length=256)
        encrypted_dek = await self.encrypt_dek(session, tenant_id, dek)
        return dek, encrypted_dek

    async def rotate_kek(self, session: ISession, tenant_id: typing.Any) -> int:
        current_version = await self._get_current_version(session, tenant_id)
        new_version = current_version + 1
        kek = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(self._NONCE_SIZE)
        encrypted_kek = nonce + self._aesgcm.encrypt(nonce, kek, None)
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._insert_sql, [str(tenant_id), new_version, encrypted_kek])
        return new_version

    async def rewrap_dek(self, session: ISession, tenant_id: typing.Any, encrypted_dek: bytes) -> bytes:
        dek = await self.decrypt_dek(session, tenant_id, encrypted_dek)
        return await self.encrypt_dek(session, tenant_id, dek)

    async def delete_kek(self, session: ISession, tenant_id: typing.Any) -> None:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._delete_sql, [str(tenant_id)])

    async def _get_current_kek(self, session: ISession, tenant_id: typing.Any) -> tuple[int, bytes]:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._select_current_sql, [str(tenant_id)])
            row = await acursor.fetchone()
        if row is None:
            raise KeyError(tenant_id)
        key_version, encrypted_kek = row[0], row[1]
        nonce = encrypted_kek[:self._NONCE_SIZE]
        kek = self._aesgcm.decrypt(nonce, encrypted_kek[self._NONCE_SIZE:], None)
        return key_version, kek

    async def _get_kek(self, session: ISession, tenant_id: typing.Any, key_version: int) -> bytes:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._select_version_sql, [str(tenant_id), key_version])
            row = await acursor.fetchone()
        if row is None:
            raise KeyError(tenant_id)
        encrypted_kek = row[0]
        nonce = encrypted_kek[:self._NONCE_SIZE]
        return self._aesgcm.decrypt(nonce, encrypted_kek[self._NONCE_SIZE:], None)

    async def _get_current_version(self, session: ISession, tenant_id: typing.Any) -> int:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._select_current_sql, [str(tenant_id)])
            row = await acursor.fetchone()
        return row[0] if row else 0

    async def setup(self, session: ISession) -> None:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(
                self._create_table_sql % (self._table, self._table)
            )

    async def cleanup(self, session: ISession) -> None:
        pass
