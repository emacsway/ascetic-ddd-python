import unittest
from unittest import IsolatedAsyncioTestCase

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ascetic_ddd.kms.kms import PgKeyManagementService
from ascetic_ddd.seedwork.infrastructure.repository.dek_store import DekStore
from ascetic_ddd.seedwork.infrastructure.repository.exceptions import DekNotFound
from ascetic_ddd.seedwork.infrastructure.repository.stream_id import StreamId
from ascetic_ddd.utils.tests.db import make_pg_session_pool


class TestPgKeyManagementService(PgKeyManagementService):
    _table = "kms_keys_test"


class TestDekStore(DekStore):
    _table = "stream_deks_test"


class DekStoreIntegrationTestCase(IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self._master_key = AESGCM.generate_key(bit_length=256)
        self._session_pool = await make_pg_session_pool()
        self._kms = TestPgKeyManagementService(self._master_key)
        self._dek_store = TestDekStore(self._kms)
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._kms.setup(session)
                await self._dek_store.setup(session)
                async with session.connection.cursor() as cursor:
                    await cursor.execute("TRUNCATE TABLE %s" % self._kms._table)
                    await cursor.execute("TRUNCATE TABLE %s" % self._dek_store._table)

    async def asyncTearDown(self):
        async with self._session_pool.session() as session:
            async with session.atomic():
                async with session.connection.cursor() as cursor:
                    await cursor.execute("DROP TABLE IF EXISTS %s" % self._dek_store._table)
                    await cursor.execute("DROP TABLE IF EXISTS %s" % self._kms._table)
        await self._session_pool._pool.close()

    def _make_stream_id(self, tenant_id="1", stream_type="Order", stream_id="order-1"):
        return StreamId(tenant_id=tenant_id, stream_type=stream_type, stream_id=stream_id)

    async def test_get_or_create_creates_cipher(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                cipher = await self._dek_store.get_or_create(session, stream_id)
                plaintext = b"hello world"
                encrypted = cipher.encrypt(plaintext)
                self.assertNotEqual(encrypted, plaintext)
                # Version prefix is 4 bytes, version 1
                version = int.from_bytes(encrypted[:DekStore._VERSION_SIZE], "big")
                self.assertEqual(version, 1)

    async def test_get_or_create_returns_same_cipher(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                cipher1 = await self._dek_store.get_or_create(session, stream_id)
                cipher2 = await self._dek_store.get_or_create(session, stream_id)
                plaintext = b"hello"
                encrypted = cipher1.encrypt(plaintext)
                decrypted = cipher2.decrypt(encrypted)
                self.assertEqual(decrypted, plaintext)

    async def test_get_existing_cipher(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                cipher = await self._dek_store.get_or_create(session, stream_id)
                plaintext = b"hello"
                encrypted = cipher.encrypt(plaintext)
                version = int.from_bytes(encrypted[:DekStore._VERSION_SIZE], "big")
                loaded_cipher = await self._dek_store.get(session, stream_id, version)
                decrypted = loaded_cipher.decrypt(encrypted)
                self.assertEqual(decrypted, plaintext)

    async def test_get_missing_dek_raises_error(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                with self.assertRaises(DekNotFound):
                    await self._dek_store.get(session, stream_id, 1)

    async def test_different_streams_get_different_ciphers(self):
        stream_id_1 = self._make_stream_id(stream_id="order-1")
        stream_id_2 = self._make_stream_id(stream_id="order-2")
        async with self._session_pool.session() as session:
            async with session.atomic():
                cipher1 = await self._dek_store.get_or_create(session, stream_id_1)
                cipher2 = await self._dek_store.get_or_create(session, stream_id_2)
                plaintext = b"hello"
                encrypted1 = cipher1.encrypt(plaintext)
                with self.assertRaises(Exception):
                    cipher2.decrypt(encrypted1)

    async def test_different_tenants_get_different_ciphers(self):
        stream_id_1 = self._make_stream_id(tenant_id="1")
        stream_id_2 = self._make_stream_id(tenant_id="2")
        async with self._session_pool.session() as session:
            async with session.atomic():
                cipher1 = await self._dek_store.get_or_create(session, stream_id_1)
                cipher2 = await self._dek_store.get_or_create(session, stream_id_2)
                plaintext = b"hello"
                encrypted1 = cipher1.encrypt(plaintext)
                with self.assertRaises(Exception):
                    cipher2.decrypt(encrypted1)

    async def test_dek_survives_kek_rotation(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                cipher = await self._dek_store.get_or_create(session, stream_id)
                plaintext = b"hello"
                encrypted = cipher.encrypt(plaintext)
                await self._kms.rotate_kek(session, stream_id.tenant_id)
                version = int.from_bytes(encrypted[:DekStore._VERSION_SIZE], "big")
                loaded_cipher = await self._dek_store.get(session, stream_id, version)
                decrypted = loaded_cipher.decrypt(encrypted)
                self.assertEqual(decrypted, plaintext)

    async def test_delete(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._dek_store.get_or_create(session, stream_id)
                await self._dek_store.delete(session, stream_id)
                with self.assertRaises(DekNotFound):
                    await self._dek_store.get(session, stream_id, 1)

    async def test_rewrap_after_kek_rotation(self):
        stream_id_1 = self._make_stream_id(stream_id="order-1")
        stream_id_2 = self._make_stream_id(stream_id="order-2")
        async with self._session_pool.session() as session:
            async with session.atomic():
                cipher1 = await self._dek_store.get_or_create(session, stream_id_1)
                cipher2 = await self._dek_store.get_or_create(session, stream_id_2)
                plaintext = b"hello"
                encrypted1 = cipher1.encrypt(plaintext)
                encrypted2 = cipher2.encrypt(plaintext)
                await self._kms.rotate_kek(session, "1")
                count = await self._dek_store.rewrap(session, "1")
                self.assertEqual(count, 2)
                v1 = int.from_bytes(encrypted1[:DekStore._VERSION_SIZE], "big")
                v2 = int.from_bytes(encrypted2[:DekStore._VERSION_SIZE], "big")
                loaded1 = await self._dek_store.get(session, stream_id_1, v1)
                loaded2 = await self._dek_store.get(session, stream_id_2, v2)
                self.assertEqual(loaded1.decrypt(encrypted1), plaintext)
                self.assertEqual(loaded2.decrypt(encrypted2), plaintext)

    async def test_get_all_decrypts_all_versions(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                cipher_v1 = await self._dek_store.get_or_create(session, stream_id)
                plaintext = b"hello"
                encrypted_v1 = cipher_v1.encrypt(plaintext)
                composite = await self._dek_store.get_all(session, stream_id)
                self.assertEqual(composite.decrypt(encrypted_v1), plaintext)

    async def test_get_all_encrypts_with_latest_version(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._dek_store.get_or_create(session, stream_id)
                composite = await self._dek_store.get_all(session, stream_id)
                plaintext = b"hello"
                encrypted = composite.encrypt(plaintext)
                version = int.from_bytes(encrypted[:DekStore._VERSION_SIZE], "big")
                self.assertEqual(version, 1)
                self.assertEqual(composite.decrypt(encrypted), plaintext)

    async def test_get_all_missing_raises_error(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                with self.assertRaises(DekNotFound):
                    await self._dek_store.get_all(session, stream_id)

    async def test_crypto_shredding(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._dek_store.get_or_create(session, stream_id)
                await self._kms.delete_kek(session, stream_id.tenant_id)
                with self.assertRaises(Exception):
                    await self._dek_store.get(session, stream_id, 1)


if __name__ == '__main__':
    unittest.main()
