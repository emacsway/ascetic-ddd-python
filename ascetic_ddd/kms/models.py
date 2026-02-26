import os
import typing
import datetime
from abc import ABCMeta, abstractmethod
from enum import Enum

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = ('MasterKey', 'Kek', 'Algorithm', 'ICipher', 'Aes256GcmCipher', )


class Algorithm(str, Enum):
    AES_256_GCM = "AES-256-GCM"


class ICipher(metaclass=ABCMeta):
    @abstractmethod
    def encrypt(self, plaintext: bytes) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def decrypt(self, ciphertext: bytes) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def generate_key(self) -> bytes:
        raise NotImplementedError


class Aes256GcmCipher(ICipher):
    _NONCE_SIZE = 12

    def __init__(self, key: bytes, aad: bytes | None = None) -> None:
        self._aesgcm = AESGCM(key)
        self._aad = aad

    def encrypt(self, plaintext: bytes) -> bytes:
        nonce = os.urandom(self._NONCE_SIZE)
        return nonce + self._aesgcm.encrypt(nonce, plaintext, self._aad)

    def decrypt(self, ciphertext: bytes) -> bytes:
        nonce = ciphertext[:self._NONCE_SIZE]
        return self._aesgcm.decrypt(nonce, ciphertext[self._NONCE_SIZE:], self._aad)

    def generate_key(self) -> bytes:
        return AESGCM.generate_key(bit_length=256)


class BaseKey:
    _KEY_VERSION_SIZE = 4
    _tenant_id: typing.Any
    _key: bytes
    _algorithm: Algorithm
    _version: int

    def __init__(
            self,
            tenant_id: typing.Any,
            key: bytes,
            version: int = 1,
            algorithm: Algorithm = Algorithm.AES_256_GCM,
    ):
        self._tenant_id = tenant_id
        self._key = key
        self._algorithm = algorithm
        self._version = version

    @property
    def tenant_id(self) -> typing.Any:
        return self._tenant_id

    @property
    def version(self) -> int:
        return self._version

    @property
    def algorithm(self) -> Algorithm:
        return self._algorithm

    def encrypt(self, plaintext: bytes) -> bytes:
        version_bytes = self._version.to_bytes(self._KEY_VERSION_SIZE, "big")
        return version_bytes + self._cipher.encrypt(plaintext)

    @classmethod
    def extract_key_version(cls, ciphertext: bytes) -> int:
        return int.from_bytes(ciphertext[:cls._KEY_VERSION_SIZE], "big")

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._cipher.decrypt(ciphertext[self._KEY_VERSION_SIZE:])

    def rewrap(self, ciphertext: bytes) -> bytes:
        plaintext = self.decrypt(ciphertext)
        return self.encrypt(plaintext)

    def generate_key(self) -> tuple[bytes, bytes]:
        key = self._cipher.generate_key()
        return key, self.encrypt(key)

    @property
    def _aad(self) -> bytes:
        return str(self._tenant_id).encode("utf-8")

    @property
    def _cipher(self) -> ICipher:
        if self._algorithm == Algorithm.AES_256_GCM:
            return Aes256GcmCipher(self._key, self._aad)
        raise NotImplementedError(self._algorithm)

    @staticmethod
    def now():
        return datetime.datetime.now(datetime.timezone.utc)


class MasterKey(BaseKey):

    def generate_obj(self, **kwargs) -> 'Kek':
        key, encrypted_key = self.generate_key()
        return Kek(
            key=key,
            encrypted_key=encrypted_key,
            **kwargs
        )

    def load_obj(self, **kwargs) -> 'Kek':
        key = self.decrypt(kwargs['encrypted_key'])
        return Kek(
            key=key,
            **kwargs
        )

    def rotate_obj(self, obj: 'Kek') -> 'Kek':
        key, encrypted_key = self.generate_key()
        return Kek(
            tenant_id=obj.tenant_id,
            key=key,
            encrypted_key=encrypted_key,
            version=obj.version + 1,
            algorithm=obj.algorithm,
            created_at=self.now(),
        )


class Kek(BaseKey):
    _encrypted_key: bytes
    _created_at: datetime.datetime

    def __init__(
            self,
            tenant_id: typing.Any,
            key: bytes,
            encrypted_key: bytes,
            version: int = 1,
            algorithm: Algorithm = Algorithm.AES_256_GCM,
            created_at: datetime.datetime | None = None,
    ):
        self._encrypted_key = encrypted_key
        self._created_at = created_at or self.now()
        super().__init__(
            tenant_id=tenant_id,
            key=key,
            version=version,
            algorithm=algorithm,
        )

    @property
    def encrypted_key(self) -> bytes:
        return self._encrypted_key

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at
