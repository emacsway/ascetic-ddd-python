import functools
import json

from psycopg.types.json import Jsonb

from ascetic_ddd.kms.interfaces import IKeyManagementService
from ascetic_ddd.kms.models import Algorithm, ICipher, Aes256GcmCipher
from ascetic_ddd.seedwork.infrastructure.repository.exceptions import DekNotFound
from ascetic_ddd.seedwork.infrastructure.repository.interfaces import IDekStore
from ascetic_ddd.seedwork.infrastructure.repository.stream_id import StreamId
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.session.pg_session import extract_connection
from ascetic_ddd.utils.json import JSONEncoder

__all__ = ("DekStore",)


class _VersionedCipher(ICipher):
    _VERSION_SIZE = 4

    def __init__(self, version: int, cipher: ICipher) -> None:
        self._version = version
        self._cipher = cipher

    def encrypt(self, plaintext: bytes) -> bytes:
        version_bytes = self._version.to_bytes(self._VERSION_SIZE, "big")
        return version_bytes + self._cipher.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._cipher.decrypt(ciphertext[self._VERSION_SIZE:])

    def generate_key(self) -> bytes:
        return self._cipher.generate_key()


class _CompositeVersionedCipher(ICipher):
    _VERSION_SIZE = 4

    def __init__(self, latest_version: int, ciphers: dict[int, ICipher]) -> None:
        self._latest_version = latest_version
        self._ciphers = ciphers

    def encrypt(self, plaintext: bytes) -> bytes:
        version_bytes = self._latest_version.to_bytes(self._VERSION_SIZE, "big")
        return version_bytes + self._ciphers[self._latest_version].encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        version = int.from_bytes(ciphertext[:self._VERSION_SIZE], "big")
        try:
            return self._ciphers[version].decrypt(ciphertext[self._VERSION_SIZE:])
        except KeyError:
            raise DekNotFound(None, version)

    def generate_key(self) -> bytes:
        return self._ciphers[self._latest_version].generate_key()


class DekStore(IDekStore):
    _extract_connection = staticmethod(extract_connection)
    _table = "stream_deks"
    _ALGORITHM = Algorithm.AES_256_GCM

    _select_latest_sql = """
        SELECT version, encrypted_dek, algorithm FROM %s
        WHERE tenant_id = %%s AND stream_type = %%s AND stream_id = %%s
        ORDER BY version DESC LIMIT 1
    """
    _select_version_sql = """
        SELECT encrypted_dek, algorithm FROM %s
        WHERE tenant_id = %%s AND stream_type = %%s AND stream_id = %%s AND version = %%s
    """
    _select_all_sql = """
        SELECT version, encrypted_dek, algorithm FROM %s
        WHERE tenant_id = %%s AND stream_type = %%s AND stream_id = %%s
        ORDER BY version
    """
    _insert_sql = """
        INSERT INTO %s (tenant_id, stream_type, stream_id, version, encrypted_dek, algorithm)
        VALUES (%%s, %%s, %%s, %%s, %%s, %%s)
    """
    _delete_sql = """
        DELETE FROM %s
        WHERE tenant_id = %%s AND stream_type = %%s AND stream_id = %%s
    """
    _select_by_tenant_sql = """
        SELECT stream_type, stream_id, version, encrypted_dek FROM %s
        WHERE tenant_id = %%s
    """
    _update_dek_sql = """
        UPDATE %s SET encrypted_dek = %%s
        WHERE tenant_id = %%s AND stream_type = %%s AND stream_id = %%s AND version = %%s
    """
    _create_table_sql = """
        CREATE TABLE IF NOT EXISTS %s (
            tenant_id varchar(128) NOT NULL,
            stream_type varchar(128) NOT NULL,
            stream_id jsonb NOT NULL,
            version integer NOT NULL,
            encrypted_dek bytea NOT NULL,
            algorithm varchar(32) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT %s_pk PRIMARY KEY (tenant_id, stream_type, stream_id, version)
        )
    """

    def __init__(self, kms: IKeyManagementService) -> None:
        self._kms = kms

    async def get_or_create(self, session: ISession, stream_id: StreamId) -> ICipher:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._select_latest_sql % self._table, [
                stream_id.tenant_id, stream_id.stream_type, self._encode(stream_id.stream_id),
            ])
            row = await acursor.fetchone()
        if row is not None:
            version, encrypted_dek, algorithm = row
            dek = await self._kms.decrypt_dek(session, stream_id.tenant_id, encrypted_dek)
            return self._make_cipher(dek, stream_id, version, algorithm)
        dek, encrypted_dek = await self._kms.generate_dek(session, stream_id.tenant_id)
        await self._insert(session, stream_id, 1, encrypted_dek)
        return self._make_cipher(dek, stream_id, 1, self._ALGORITHM.value)

    async def get(self, session: ISession, stream_id: StreamId, key_version: int) -> ICipher:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._select_version_sql % self._table, [
                stream_id.tenant_id, stream_id.stream_type, self._encode(stream_id.stream_id),
                key_version,
            ])
            row = await acursor.fetchone()
        if row is None:
            raise DekNotFound(stream_id, key_version)
        encrypted_dek, algorithm = row
        dek = await self._kms.decrypt_dek(session, stream_id.tenant_id, encrypted_dek)
        return self._make_cipher(dek, stream_id, key_version, algorithm)

    async def get_all(self, session: ISession, stream_id: StreamId) -> ICipher:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._select_all_sql % self._table, [
                stream_id.tenant_id, stream_id.stream_type, self._encode(stream_id.stream_id),
            ])
            rows = await acursor.fetchall()
        if not rows:
            raise DekNotFound(stream_id)
        ciphers = {}
        latest_version = 0
        for version, encrypted_dek, algorithm in rows:
            dek = await self._kms.decrypt_dek(session, stream_id.tenant_id, encrypted_dek)
            ciphers[version] = self._make_raw_cipher(dek, stream_id, algorithm)
            if version > latest_version:
                latest_version = version
        return _CompositeVersionedCipher(latest_version, ciphers)

    async def _insert(self, session: ISession, stream_id: StreamId, version: int, encrypted_dek: bytes) -> None:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._insert_sql % self._table, [
                stream_id.tenant_id, stream_id.stream_type, self._encode(stream_id.stream_id),
                version, encrypted_dek, self._ALGORITHM.value,
            ])

    async def rewrap(self, session: ISession, tenant_id) -> int:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._select_by_tenant_sql % self._table, [tenant_id])
            rows = await acursor.fetchall()
        count = 0
        for stream_type, stream_id, version, encrypted_dek in rows:
            new_encrypted_dek = await self._kms.rewrap_dek(session, tenant_id, encrypted_dek)
            async with self._extract_connection(session).cursor() as acursor:
                await acursor.execute(self._update_dek_sql % self._table, [
                    new_encrypted_dek, tenant_id, stream_type, self._encode(stream_id), version,
                ])
            count += 1
        return count

    async def delete(self, session: ISession, stream_id: StreamId) -> None:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(self._delete_sql % self._table, [
                stream_id.tenant_id, stream_id.stream_type, self._encode(stream_id.stream_id),
            ])

    def _make_cipher(self, dek: bytes, stream_id: StreamId, version: int, algorithm: str) -> ICipher:
        return _VersionedCipher(version, self._make_raw_cipher(dek, stream_id, algorithm))

    def _make_raw_cipher(self, dek: bytes, stream_id: StreamId, algorithm: str) -> ICipher:
        aad = str(stream_id).encode("utf-8")
        algo = Algorithm(algorithm)
        if algo == Algorithm.AES_256_GCM:
            return Aes256GcmCipher(dek, aad)
        raise NotImplementedError(algo)

    @staticmethod
    def _encode(obj):
        dumps = functools.partial(json.dumps, cls=JSONEncoder)
        return Jsonb(obj, dumps)

    async def setup(self, session: ISession) -> None:
        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(
                self._create_table_sql % (self._table, self._table)
            )

    async def cleanup(self, session: ISession) -> None:
        pass
