import os
import typing
import datetime
from abc import ABCMeta, abstractmethod
from enum import Enum

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = ('Kek', 'Algorithm',)


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


class Kek:
    _KEY_VERSION_SIZE = 4
    _master_key: bytes
    _master_algorithm: Algorithm
    _kek_version: int
    _tenant_id: typing.Any
    _kek_algorithm: Algorithm
    _created_at: datetime.datetime
    _encrypted_kek: bytes | None

    def __init__(
            self,
            master_key: bytes,
            tenant_id: typing.Any,
            kek_version: int = 1,
            encrypted_kek: bytes | None = None,
            kek_algorithm: Algorithm = Algorithm.AES_256_GCM,
            master_algorithm: Algorithm = Algorithm.AES_256_GCM,
            created_at: datetime.datetime | None = None,
    ):
        if kek_version != 1:
            assert encrypted_kek is not None
        self._master_key = master_key
        self._master_algorithm = master_algorithm
        self._tenant_id = tenant_id
        self._kek_version = kek_version
        self._encrypted_kek = encrypted_kek
        self._kek_algorithm = kek_algorithm
        self._created_at = created_at or self.now()

    @property
    def master_algorithm(self) -> Algorithm:
        return self._master_algorithm

    @property
    def tenant_id(self) -> typing.Any:
        return self._tenant_id

    @property
    def kek_version(self) -> int:
        return self._kek_version

    @property
    def kek_algorithm(self) -> Algorithm:
        return self._kek_algorithm

    @property
    def encrypted_kek(self) -> bytes | None:
        if self._encrypted_kek is None:
            kek_bytes = self._master_cipher.generate_key()
            self._encrypted_kek = self._master_cipher.encrypt(kek_bytes)
        return self._encrypted_kek

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    def encrypt_dek(self, dek: bytes) -> bytes:
        version_bytes = self._kek_version.to_bytes(self._KEY_VERSION_SIZE, "big")
        return version_bytes + self._kek_cipher.encrypt(dek)

    def decrypt_dek(self, encrypted_dek: bytes) -> bytes:
        return self._kek_cipher.decrypt(encrypted_dek[self._KEY_VERSION_SIZE:])

    def generate_dek(self) -> tuple[bytes, bytes]:
        dek = self._kek_cipher.generate_key()
        return dek, self.encrypt_dek(dek)

    def rewrap_dek(self, encrypted_dek: bytes) -> bytes:
        dek = self.decrypt_dek(encrypted_dek)
        return self.encrypt_dek(dek)

    def rotate(self) -> 'Kek':
        kek_bytes = self._master_cipher.generate_key()
        encrypted_kek = self._master_cipher.encrypt(kek_bytes)
        return Kek(
            master_key=self._master_key,
            master_algorithm=self._master_algorithm,
            tenant_id=self._tenant_id,
            kek_version=self._kek_version + 1,
            encrypted_kek=encrypted_kek,
            kek_algorithm=self._kek_algorithm,
            created_at=self.now(),
        )

    @property
    def _aad(self) -> bytes:
        return str(self._tenant_id).encode("utf-8")

    @property
    def _master_cipher(self) -> ICipher:
        if self._master_algorithm == Algorithm.AES_256_GCM:
            return Aes256GcmCipher(self._master_key, self._aad)
        raise NotImplementedError(self._kek_algorithm)

    @property
    def _kek_cipher(self) -> ICipher:
        kek_bytes = self._master_cipher.decrypt(self.encrypted_kek)
        if self._kek_algorithm == Algorithm.AES_256_GCM:
            return Aes256GcmCipher(kek_bytes, self._aad)
        raise NotImplementedError(self._kek_algorithm)

    @staticmethod
    def now():
        return datetime.datetime.now(datetime.timezone.utc)
