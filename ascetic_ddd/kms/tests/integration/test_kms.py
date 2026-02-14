import unittest
from unittest import IsolatedAsyncioTestCase

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ascetic_ddd.kms.kms import PgKeyManagementService
from ascetic_ddd.utils.tests.db import make_pg_session_pool


class TestPgKeyManagementService(PgKeyManagementService):
    _table = "kms_keys_test"


class KmsIntegrationTestCase(IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self._master_key = AESGCM.generate_key(bit_length=256)
        self._session_pool = await make_pg_session_pool()
        self._kms = TestPgKeyManagementService(self._master_key)
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._kms.setup(session)
                async with session.connection.cursor() as cursor:
                    await cursor.execute("TRUNCATE TABLE %s" % self._kms._table)

    async def asyncTearDown(self):
        async with self._session_pool.session() as session:
            async with session.atomic():
                async with session.connection.cursor() as cursor:
                    await cursor.execute("DROP TABLE IF EXISTS %s" % self._kms._table)
        await self._session_pool._pool.close()

    async def _create_kek(self, session, tenant_id):
        return await self._kms.rotate_kek(session, tenant_id)

    async def test_rotate_and_encrypt_decrypt(self):
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._create_kek(session, "1")
                dek = AESGCM.generate_key(bit_length=256)
                encrypted_dek = await self._kms.encrypt_dek(session, "1", dek)
                decrypted_dek = await self._kms.decrypt_dek(session, "1", encrypted_dek)
                self.assertEqual(dek, decrypted_dek)

    async def test_generate_dek(self):
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._create_kek(session, "1")
                dek, encrypted_dek = await self._kms.generate_dek(session, "1")
                self.assertEqual(len(dek), 32)
                decrypted_dek = await self._kms.decrypt_dek(session, "1", encrypted_dek)
                self.assertEqual(dek, decrypted_dek)

    async def test_rotate_kek_increments_version(self):
        async with self._session_pool.session() as session:
            async with session.atomic():
                v1 = await self._kms.rotate_kek(session, "1")
                v2 = await self._kms.rotate_kek(session, "1")
                self.assertEqual(v1, 1)
                self.assertEqual(v2, 2)

    async def test_decrypt_after_rotation(self):
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._create_kek(session, "1")
                dek = AESGCM.generate_key(bit_length=256)
                encrypted_dek_v1 = await self._kms.encrypt_dek(session, "1", dek)

                await self._kms.rotate_kek(session, "1")

                decrypted = await self._kms.decrypt_dek(session, "1", encrypted_dek_v1)
                self.assertEqual(dek, decrypted)

    async def test_rewrap_dek(self):
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._create_kek(session, "1")
                dek = AESGCM.generate_key(bit_length=256)
                encrypted_dek_v1 = await self._kms.encrypt_dek(session, "1", dek)

                await self._kms.rotate_kek(session, "1")
                encrypted_dek_v2 = await self._kms.rewrap_dek(session, "1", encrypted_dek_v1)

                self.assertNotEqual(encrypted_dek_v1, encrypted_dek_v2)
                decrypted = await self._kms.decrypt_dek(session, "1", encrypted_dek_v2)
                self.assertEqual(dek, decrypted)

    async def test_delete_kek_crypto_shredding(self):
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._create_kek(session, "1")
                dek = AESGCM.generate_key(bit_length=256)
                encrypted_dek = await self._kms.encrypt_dek(session, "1", dek)

                await self._kms.delete_kek(session, "1")

                with self.assertRaises(Exception):
                    await self._kms.decrypt_dek(session, "1", encrypted_dek)

    async def test_tenant_isolation(self):
        async with self._session_pool.session() as session:
            async with session.atomic():
                await self._create_kek(session, "1")
                await self._create_kek(session, "2")

                dek = AESGCM.generate_key(bit_length=256)
                encrypted_dek = await self._kms.encrypt_dek(session, "1", dek)

                decrypted = await self._kms.decrypt_dek(session, "1", encrypted_dek)
                self.assertEqual(dek, decrypted)

                with self.assertRaises(Exception):
                    await self._kms.decrypt_dek(session, 2, encrypted_dek)


if __name__ == '__main__':
    unittest.main()
