import unittest
from unittest import IsolatedAsyncioTestCase

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ascetic_ddd.kms.kms import PgKeyManagementService
from ascetic_ddd.seedwork.infrastructure.repository.dek_store import PgDekStore
from ascetic_ddd.seedwork.infrastructure.repository.stream_id import StreamId
from ascetic_ddd.utils.tests.db import make_pg_session_pool


class TestPgKeyManagementService(PgKeyManagementService):
    _table = "kms_keys_test"

    _select_current_sql = """
        SELECT key_version, encrypted_kek FROM kms_keys_test
        WHERE tenant_id = %s ORDER BY key_version DESC LIMIT 1
    """
    _select_version_sql = """
        SELECT encrypted_kek FROM kms_keys_test
        WHERE tenant_id = %s AND key_version = %s
    """
    _insert_sql = """
        INSERT INTO kms_keys_test (tenant_id, key_version, encrypted_kek)
        VALUES (%s, %s, %s)
    """
    _delete_sql = "DELETE FROM kms_keys_test WHERE tenant_id = %s"


class TestPgDekStore(PgDekStore):
    _table = "stream_deks_test"

    _select_sql = """
        SELECT encrypted_dek FROM stream_deks_test
        WHERE tenant_id = %s AND stream_type = %s AND stream_id = %s
    """
    _insert_sql = """
        INSERT INTO stream_deks_test (tenant_id, stream_type, stream_id, encrypted_dek)
        VALUES (%s, %s, %s, %s)
    """


class DekStoreIntegrationTestCase(IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self._master_key = AESGCM.generate_key(bit_length=256)
        self._session_pool = await make_pg_session_pool()
        self._kms = TestPgKeyManagementService(self._master_key)
        self._dek_store = TestPgDekStore(self._kms)
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

    async def test_get_or_create_creates_dek(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                dek = await self._dek_store.get_or_create(session, stream_id)
                self.assertIsInstance(dek, bytes)
                self.assertEqual(len(dek), 32)

    async def test_get_or_create_returns_same_dek(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                dek1 = await self._dek_store.get_or_create(session, stream_id)
                dek2 = await self._dek_store.get_or_create(session, stream_id)
                self.assertEqual(dek1, dek2)

    async def test_get_existing_dek(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                dek = await self._dek_store.get_or_create(session, stream_id)
                loaded_dek = await self._dek_store.get(session, stream_id)
                self.assertEqual(dek, loaded_dek)

    async def test_get_missing_dek_raises_key_error(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                with self.assertRaises(KeyError):
                    await self._dek_store.get(session, stream_id)

    async def test_different_streams_get_different_deks(self):
        stream_id_1 = self._make_stream_id(stream_id="order-1")
        stream_id_2 = self._make_stream_id(stream_id="order-2")
        async with self._session_pool.session() as session:
            async with session.atomic():
                dek1 = await self._dek_store.get_or_create(session, stream_id_1)
                dek2 = await self._dek_store.get_or_create(session, stream_id_2)
                self.assertNotEqual(dek1, dek2)

    async def test_different_tenants_get_different_deks(self):
        stream_id_1 = self._make_stream_id(tenant_id="1")
        stream_id_2 = self._make_stream_id(tenant_id="2")
        async with self._session_pool.session() as session:
            async with session.atomic():
                dek1 = await self._dek_store.get_or_create(session, stream_id_1)
                dek2 = await self._dek_store.get_or_create(session, stream_id_2)
                self.assertNotEqual(dek1, dek2)

    async def test_dek_survives_kek_rotation(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                dek = await self._dek_store.get_or_create(session, stream_id)
                await self._kms.rotate_kek(session, stream_id.tenant_id)
                loaded_dek = await self._dek_store.get(session, stream_id)
                self.assertEqual(dek, loaded_dek)

    async def test_crypto_shredding(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._dek_store.get_or_create(session, stream_id)
                await self._kms.delete_kek(session, stream_id.tenant_id)
                with self.assertRaises(Exception):
                    await self._dek_store.get(session, stream_id)


if __name__ == '__main__':
    unittest.main()
