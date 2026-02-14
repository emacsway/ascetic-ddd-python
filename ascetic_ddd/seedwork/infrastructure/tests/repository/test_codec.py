import unittest
import uuid
import datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ascetic_ddd.seedwork.infrastructure.repository.codec import (
    JsonCodec,
    ZlibCompressor,
    AesGcmEncryptor,
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


class ZlibCompressorTestCase(unittest.TestCase):

    def test_encode_decode(self):
        codec = ZlibCompressor(JsonCodec())
        obj = {"name": "test", "value": 42}
        encoded = codec.encode(obj)
        self.assertIsInstance(encoded, bytes)
        self.assertEqual(codec.decode(encoded), obj)

    def test_compressed_differs_from_plain(self):
        plain_codec = JsonCodec()
        zlib_codec = ZlibCompressor(JsonCodec())
        obj = {"name": "test", "value": 42}
        self.assertNotEqual(plain_codec.encode(obj), zlib_codec.encode(obj))


class AesGcmEncryptorTestCase(unittest.TestCase):

    def setUp(self):
        self._key = AESGCM.generate_key(bit_length=256)

    def test_encode_decode(self):
        codec = AesGcmEncryptor(self._key, JsonCodec())
        obj = {"name": "test", "value": 42}
        encoded = codec.encode(obj)
        self.assertIsInstance(encoded, bytes)
        self.assertEqual(codec.decode(encoded), obj)

    def test_encrypted_differs_from_plain(self):
        plain_codec = JsonCodec()
        enc_codec = AesGcmEncryptor(self._key, JsonCodec())
        obj = {"name": "test", "value": 42}
        self.assertNotEqual(plain_codec.encode(obj), enc_codec.encode(obj))

    def test_different_nonce_each_encode(self):
        codec = AesGcmEncryptor(self._key, JsonCodec())
        obj = {"name": "test"}
        encoded1 = codec.encode(obj)
        encoded2 = codec.encode(obj)
        self.assertNotEqual(encoded1, encoded2)

    def test_wrong_key_fails(self):
        codec = AesGcmEncryptor(self._key, JsonCodec())
        obj = {"name": "secret"}
        encoded = codec.encode(obj)
        wrong_key = AESGCM.generate_key(bit_length=256)
        wrong_codec = AesGcmEncryptor(wrong_key, JsonCodec())
        with self.assertRaises(Exception):
            wrong_codec.decode(encoded)

    def test_with_zlib(self):
        codec = AesGcmEncryptor(self._key, ZlibCompressor(JsonCodec()))
        obj = {"name": "test", "value": 42}
        encoded = codec.encode(obj)
        self.assertEqual(codec.decode(encoded), obj)


if __name__ == '__main__':
    unittest.main()
