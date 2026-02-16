import os
import unittest
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

from dotenv import load_dotenv

from ascetic_ddd.kms.vault_service import VaultTransitService
from ascetic_ddd.session.rest_session import RestSessionPool

_config_env = Path(__file__).parents[4] / 'config' / '.env'
load_dotenv(_config_env)


class VaultTransitServiceIntegrationTestCase(IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        vault_addr = os.environ.get("TEST_VAULT_ADDR", "http://localhost:8200")
        vault_token = os.environ.get("TEST_VAULT_TOKEN", "test-root-token")
        self._session_pool = RestSessionPool()
        self._kms = VaultTransitService(
            vault_addr=vault_addr,
            vault_token=vault_token,
        )
        self._tenant_id = "test-tenant-1"
        self._tenant_id_2 = "test-tenant-2"

    async def asyncTearDown(self):
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                await self._kms.delete_kek(tx_session, self._tenant_id)
                await self._kms.delete_kek(tx_session, self._tenant_id_2)

    async def test_rotate_and_encrypt_decrypt(self):
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                await self._kms.rotate_kek(tx_session, self._tenant_id)
                dek = os.urandom(32)
                encrypted_dek = await self._kms.encrypt_dek(tx_session, self._tenant_id, dek)
                decrypted_dek = await self._kms.decrypt_dek(tx_session, self._tenant_id, encrypted_dek)
                self.assertEqual(dek, decrypted_dek)

    async def test_generate_dek(self):
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                await self._kms.rotate_kek(tx_session, self._tenant_id)
                dek, encrypted_dek = await self._kms.generate_dek(tx_session, self._tenant_id)
                self.assertEqual(len(dek), 32)
                decrypted_dek = await self._kms.decrypt_dek(tx_session, self._tenant_id, encrypted_dek)
                self.assertEqual(dek, decrypted_dek)

    async def test_rotate_kek_increments_version(self):
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                v1 = await self._kms.rotate_kek(tx_session, self._tenant_id)
                v2 = await self._kms.rotate_kek(tx_session, self._tenant_id)
                self.assertEqual(v1, 1)
                self.assertEqual(v2, 2)

    async def test_decrypt_after_rotation(self):
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                await self._kms.rotate_kek(tx_session, self._tenant_id)
                dek = os.urandom(32)
                encrypted_dek_v1 = await self._kms.encrypt_dek(tx_session, self._tenant_id, dek)

                await self._kms.rotate_kek(tx_session, self._tenant_id)

                decrypted = await self._kms.decrypt_dek(tx_session, self._tenant_id, encrypted_dek_v1)
                self.assertEqual(dek, decrypted)

    async def test_rewrap_dek(self):
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                await self._kms.rotate_kek(tx_session, self._tenant_id)
                dek = os.urandom(32)
                encrypted_dek_v1 = await self._kms.encrypt_dek(tx_session, self._tenant_id, dek)

                await self._kms.rotate_kek(tx_session, self._tenant_id)
                encrypted_dek_v2 = await self._kms.rewrap_dek(tx_session, self._tenant_id, encrypted_dek_v1)

                self.assertNotEqual(encrypted_dek_v1, encrypted_dek_v2)
                decrypted = await self._kms.decrypt_dek(tx_session, self._tenant_id, encrypted_dek_v2)
                self.assertEqual(dek, decrypted)

    async def test_delete_kek_crypto_shredding(self):
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                await self._kms.rotate_kek(tx_session, self._tenant_id)
                dek = os.urandom(32)
                encrypted_dek = await self._kms.encrypt_dek(tx_session, self._tenant_id, dek)

                await self._kms.delete_kek(tx_session, self._tenant_id)

                with self.assertRaises(Exception):
                    await self._kms.decrypt_dek(tx_session, self._tenant_id, encrypted_dek)

    async def test_encrypt_auto_creates_key(self):
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                dek = os.urandom(32)
                encrypted_dek = await self._kms.encrypt_dek(tx_session, self._tenant_id, dek)
                decrypted_dek = await self._kms.decrypt_dek(tx_session, self._tenant_id, encrypted_dek)
                self.assertEqual(dek, decrypted_dek)

    async def test_tenant_isolation(self):
        async with self._session_pool.session() as session:
            async with session.atomic() as tx_session:
                await self._kms.rotate_kek(tx_session, self._tenant_id)
                await self._kms.rotate_kek(tx_session, self._tenant_id_2)

                dek = os.urandom(32)
                encrypted_dek = await self._kms.encrypt_dek(tx_session, self._tenant_id, dek)

                decrypted = await self._kms.decrypt_dek(tx_session, self._tenant_id, encrypted_dek)
                self.assertEqual(dek, decrypted)

                with self.assertRaises(Exception):
                    await self._kms.decrypt_dek(tx_session, self._tenant_id_2, encrypted_dek)


if __name__ == '__main__':
    unittest.main()
