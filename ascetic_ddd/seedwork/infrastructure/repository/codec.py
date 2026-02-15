import json
import os
import zlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ascetic_ddd.seedwork.infrastructure.repository import ICodec
from ascetic_ddd.utils.json import JSONEncoder

__all__ = ("JsonCodec", "ZlibCompressor", "AesGcmEncryptor")


class JsonCodec(ICodec):

    def encode(self, obj: dict) -> bytes:
        return json.dumps(obj, cls=JSONEncoder).encode("utf-8")

    def decode(self, data: bytes) -> dict:
        return json.loads(data)


class ZlibCompressor(ICodec):

    def __init__(self, delegate: ICodec) -> None:
        self._delegate = delegate

    def encode(self, obj: dict) -> bytes:
        return zlib.compress(self._delegate.encode(obj))

    def decode(self, data: bytes) -> dict:
        return self._delegate.decode(zlib.decompress(data))


class AesGcmEncryptor(ICodec):
    _NONCE_SIZE = 12

    def __init__(self, key: bytes, delegate: ICodec, aad: bytes = None) -> None:
        self._aesgcm = AESGCM(key)
        self._delegate = delegate
        self._aad = aad

    def encode(self, obj: dict) -> bytes:
        nonce = os.urandom(self._NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, self._delegate.encode(obj), self._aad)
        return nonce + ciphertext

    def decode(self, data: bytes) -> dict:
        nonce = data[:self._NONCE_SIZE]
        ciphertext = data[self._NONCE_SIZE:]
        return self._delegate.decode(self._aesgcm.decrypt(nonce, ciphertext, self._aad))
