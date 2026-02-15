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
                with self.assertRaises(DekNotFound):
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

    async def test_delete(self):
        stream_id = self._make_stream_id()
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._dek_store.get_or_create(session, stream_id)
                await self._dek_store.delete(session, stream_id)
                with self.assertRaises(DekNotFound):
                    await self._dek_store.get(session, stream_id)

    async def test_rewrap_after_kek_rotation(self):
        stream_id_1 = self._make_stream_id(stream_id="order-1")
        stream_id_2 = self._make_stream_id(stream_id="order-2")
        async with self._session_pool.session() as session:
            async with session.atomic():
                dek1 = await self._dek_store.get_or_create(session, stream_id_1)
                dek2 = await self._dek_store.get_or_create(session, stream_id_2)
                await self._kms.rotate_kek(session, "1")
                count = await self._dek_store.rewrap(session, "1")
                self.assertEqual(count, 2)
                self.assertEqual(await self._dek_store.get(session, stream_id_1), dek1)
                self.assertEqual(await self._dek_store.get(session, stream_id_2), dek2)

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
