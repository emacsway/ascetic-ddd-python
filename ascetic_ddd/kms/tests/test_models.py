import unittest

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ascetic_ddd.kms.models import MasterKey, Kek, Algorithm


class Aes256GcmCipherTestCase(unittest.TestCase):

    def test_encrypt_decrypt(self):
        key = AESGCM.generate_key(bit_length=256)
        master = MasterKey(tenant_id="t1", key=key)
        plaintext = b"hello world"
        ciphertext = master.encrypt(plaintext)
        self.assertEqual(master.decrypt(ciphertext), plaintext)

    def test_encrypt_produces_different_ciphertext(self):
        key = AESGCM.generate_key(bit_length=256)
        master = MasterKey(tenant_id="t1", key=key)
        plaintext = b"hello world"
        ct1 = master.encrypt(plaintext)
        ct2 = master.encrypt(plaintext)
        self.assertNotEqual(ct1, ct2)

    def test_aad_mismatch_fails(self):
        key = AESGCM.generate_key(bit_length=256)
        master1 = MasterKey(tenant_id="t1", key=key)
        master2 = MasterKey(tenant_id="t2", key=key)
        ciphertext = master1.encrypt(b"secret")
        with self.assertRaises(Exception):
            master2.decrypt(ciphertext)


class MasterKeyTestCase(unittest.TestCase):

    def setUp(self):
        self._master_key = AESGCM.generate_key(bit_length=256)
        self._tenant_id = "tenant-1"

    def test_generate_obj(self):
        master = MasterKey(tenant_id=self._tenant_id, key=self._master_key)
        kek = master.generate_obj(tenant_id=self._tenant_id)
        self.assertIsInstance(kek, Kek)
        self.assertEqual(kek.tenant_id, self._tenant_id)
        self.assertEqual(kek.version, 1)
        self.assertEqual(kek.algorithm, Algorithm.AES_256_GCM)
        self.assertIsInstance(kek.encrypted_key, bytes)

    def test_load_obj(self):
        master = MasterKey(tenant_id=self._tenant_id, key=self._master_key)
        kek = master.generate_obj(tenant_id=self._tenant_id)
        loaded = master.load_obj(
            tenant_id=self._tenant_id,
            encrypted_key=kek.encrypted_key,
            version=kek.version,
            algorithm=kek.algorithm,
            created_at=kek._created_at,
        )
        self.assertEqual(loaded.tenant_id, kek.tenant_id)
        self.assertEqual(loaded.version, kek.version)
        self.assertEqual(loaded.encrypted_key, kek.encrypted_key)

    def test_load_obj_wrong_tenant_fails(self):
        master1 = MasterKey(tenant_id="t1", key=self._master_key)
        master2 = MasterKey(tenant_id="t2", key=self._master_key)
        kek = master1.generate_obj(tenant_id="t1")
        with self.assertRaises(Exception):
            master2.load_obj(
                tenant_id="t2",
                encrypted_key=kek.encrypted_key,
            )

    def test_rotate_obj(self):
        master = MasterKey(tenant_id=self._tenant_id, key=self._master_key)
        kek = master.generate_obj(tenant_id=self._tenant_id)
        rotated = master.rotate_obj(kek)
        self.assertEqual(rotated.version, kek.version + 1)
        self.assertEqual(rotated.tenant_id, kek.tenant_id)
        self.assertEqual(rotated.algorithm, kek.algorithm)
        self.assertNotEqual(rotated.encrypted_key, kek.encrypted_key)

    def test_generate_key(self):
        master = MasterKey(tenant_id=self._tenant_id, key=self._master_key)
        key, encrypted_key = master.generate_key()
        self.assertEqual(len(key), 32)
        decrypted = master.decrypt(encrypted_key)
        self.assertEqual(key, decrypted)


class KekTestCase(unittest.TestCase):

    def setUp(self):
        self._master_key = AESGCM.generate_key(bit_length=256)
        self._tenant_id = "tenant-1"
        master = MasterKey(tenant_id=self._tenant_id, key=self._master_key)
        self._kek = master.generate_obj(tenant_id=self._tenant_id)

    def test_encrypt_decrypt(self):
        dek = AESGCM.generate_key(bit_length=256)
        encrypted = self._kek.encrypt(dek)
        decrypted = self._kek.decrypt(encrypted)
        self.assertEqual(dek, decrypted)

    def test_generate_key(self):
        dek, encrypted_dek = self._kek.generate_key()
        self.assertEqual(len(dek), 32)
        decrypted = self._kek.decrypt(encrypted_dek)
        self.assertEqual(dek, decrypted)

    def test_rewrap(self):
        dek = AESGCM.generate_key(bit_length=256)
        encrypted_v1 = self._kek.encrypt(dek)
        rewrapped = self._kek.rewrap(encrypted_v1)
        self.assertNotEqual(encrypted_v1, rewrapped)
        self.assertEqual(self._kek.decrypt(rewrapped), dek)

    def test_version_in_ciphertext(self):
        dek = AESGCM.generate_key(bit_length=256)
        encrypted = self._kek.encrypt(dek)
        version = int.from_bytes(encrypted[:4], "big")
        self.assertEqual(version, self._kek.version)

    def test_decrypt_after_rotation(self):
        master = MasterKey(tenant_id=self._tenant_id, key=self._master_key)
        dek = AESGCM.generate_key(bit_length=256)
        encrypted_v1 = self._kek.encrypt(dek)
        rotated = master.rotate_obj(self._kek)
        decrypted = self._kek.decrypt(encrypted_v1)
        self.assertEqual(dek, decrypted)
        with self.assertRaises(Exception):
            rotated.decrypt(encrypted_v1)

    def test_tenant_isolation(self):
        master = MasterKey(tenant_id="t2", key=self._master_key)
        kek2 = master.generate_obj(tenant_id="t2")
        dek = AESGCM.generate_key(bit_length=256)
        encrypted = self._kek.encrypt(dek)
        with self.assertRaises(Exception):
            kek2.decrypt(encrypted)

    def test_cross_tenant_kek_substitution_fails(self):
        master1 = MasterKey(tenant_id="t1", key=self._master_key)
        master2 = MasterKey(tenant_id="t2", key=self._master_key)
        kek1 = master1.generate_obj(tenant_id="t1")
        with self.assertRaises(Exception):
            master2.load_obj(
                tenant_id="t2",
                encrypted_key=kek1.encrypted_key,
            )


if __name__ == '__main__':
    unittest.main()
