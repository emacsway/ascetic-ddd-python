import json
import zlib

from ascetic_ddd.kms.models import ICipher
from ascetic_ddd.seedwork.infrastructure.repository import ICodec
from ascetic_ddd.utils.json import JSONEncoder

__all__ = ("JsonCodec", "ZlibCodec", "EncryptionCodec")


class JsonCodec(ICodec):

    def encode(self, obj: dict) -> bytes:
        return json.dumps(obj, cls=JSONEncoder).encode("utf-8")

    def decode(self, data: bytes) -> dict:
        return json.loads(data)


class ZlibCodec(ICodec):

    def __init__(self, delegate: ICodec) -> None:
        self._delegate = delegate

    def encode(self, obj: dict) -> bytes:
        return zlib.compress(self._delegate.encode(obj))

    def decode(self, data: bytes) -> dict:
        return self._delegate.decode(zlib.decompress(data))


class EncryptionCodec(ICodec):

    def __init__(self, cipher: ICipher, delegate: ICodec) -> None:
        self._cipher = cipher
        self._delegate = delegate

    def encode(self, obj: dict) -> bytes:
        return self._cipher.encrypt(self._delegate.encode(obj))

    def decode(self, data: bytes) -> dict:
        return self._delegate.decode(self._cipher.decrypt(data))
