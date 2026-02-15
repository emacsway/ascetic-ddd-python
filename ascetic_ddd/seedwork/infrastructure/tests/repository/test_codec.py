import unittest
import uuid
import datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ascetic_ddd.kms.models import Aes256GcmCipher
from ascetic_ddd.seedwork.infrastructure.repository.codec import (
    JsonCodec,
    ZlibCodec,
    EncryptionCodec,
)


class JsonCodecTestCase(unittest.TestCase):

    def test_encode_decode(self):
        codec = JsonCodec()
        obj = {"name": "test", "value": 42}
        encoded = codec.encode(obj)
        self.assertIsInstance(encoded, bytes)
        self.assertEqual(codec.decode(encoded), obj)

    def test_encode_uuid(self):
        codec = JsonCodec()
        uid = uuid.uuid4()
        obj = {"id": uid}
        decoded = codec.decode(codec.encode(obj))
        self.assertEqual(decoded["id"], str(uid))

    def test_encode_datetime(self):
        codec = JsonCodec()
        obj = {"occurred_at": datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)}
        decoded = codec.decode(codec.encode(obj))
        self.assertEqual(decoded["occurred_at"], "2026-01-01T12:00:00Z")


class ZlibCodecTestCase(unittest.TestCase):

    def test_encode_decode(self):
        codec = ZlibCodec(JsonCodec())
        obj = {"name": "test", "value": 42}
        encoded = codec.encode(obj)
        self.assertIsInstance(encoded, bytes)
        self.assertEqual(codec.decode(encoded), obj)

    def test_compressed_differs_from_plain(self):
        plain_codec = JsonCodec()
        zlib_codec = ZlibCodec(JsonCodec())
        obj = {"name": "test", "value": 42}
        self.assertNotEqual(plain_codec.encode(obj), zlib_codec.encode(obj))


class EncryptionCodecTestCase(unittest.TestCase):

    def setUp(self):
        self._key = AESGCM.generate_key(bit_length=256)

    def test_encode_decode(self):
        cipher = Aes256GcmCipher(self._key)
        codec = EncryptionCodec(cipher, JsonCodec())
        obj = {"name": "test", "value": 42}
        encoded = codec.encode(obj)
        self.assertIsInstance(encoded, bytes)
        self.assertEqual(codec.decode(encoded), obj)

    def test_encrypted_differs_from_plain(self):
        plain_codec = JsonCodec()
        cipher = Aes256GcmCipher(self._key)
        enc_codec = EncryptionCodec(cipher, JsonCodec())
        obj = {"name": "test", "value": 42}
        self.assertNotEqual(plain_codec.encode(obj), enc_codec.encode(obj))

    def test_different_nonce_each_encode(self):
        cipher = Aes256GcmCipher(self._key)
        codec = EncryptionCodec(cipher, JsonCodec())
        obj = {"name": "test"}
        encoded1 = codec.encode(obj)
        encoded2 = codec.encode(obj)
        self.assertNotEqual(encoded1, encoded2)

    def test_wrong_key_fails(self):
        cipher = Aes256GcmCipher(self._key)
        codec = EncryptionCodec(cipher, JsonCodec())
        obj = {"name": "secret"}
        encoded = codec.encode(obj)
        wrong_key = AESGCM.generate_key(bit_length=256)
        wrong_cipher = Aes256GcmCipher(wrong_key)
        wrong_codec = EncryptionCodec(wrong_cipher, JsonCodec())
        with self.assertRaises(Exception):
            wrong_codec.decode(encoded)

    def test_with_zlib(self):
        cipher = Aes256GcmCipher(self._key)
        codec = EncryptionCodec(cipher, ZlibCodec(JsonCodec()))
        obj = {"name": "test", "value": 42}
        encoded = codec.encode(obj)
        self.assertEqual(codec.decode(encoded), obj)

    def test_with_aad(self):
        aad = b"stream-123"
        cipher = Aes256GcmCipher(self._key, aad)
        codec = EncryptionCodec(cipher, JsonCodec())
        obj = {"name": "test"}
        encoded = codec.encode(obj)
        self.assertEqual(codec.decode(encoded), obj)
        wrong_aad_cipher = Aes256GcmCipher(self._key, b"wrong")
        wrong_codec = EncryptionCodec(wrong_aad_cipher, JsonCodec())
        with self.assertRaises(Exception):
            wrong_codec.decode(encoded)


if __name__ == '__main__':
    unittest.main()
