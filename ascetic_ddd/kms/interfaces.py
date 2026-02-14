import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.session.interfaces import ISession

__all__ = ("IKeyManagementService",)


class IKeyManagementService(metaclass=ABCMeta):

    @abstractmethod
    async def encrypt_dek(self, session: ISession, tenant_id: typing.Any, dek: bytes) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def decrypt_dek(self, session: ISession, tenant_id: typing.Any, encrypted_dek: bytes) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def generate_dek(self, session: ISession, tenant_id: typing.Any) -> tuple[bytes, bytes]:
        raise NotImplementedError

    @abstractmethod
    async def rotate_kek(self, session: ISession, tenant_id: typing.Any) -> int:
        raise NotImplementedError

    @abstractmethod
    async def rewrap_dek(self, session: ISession, tenant_id: typing.Any, encrypted_dek: bytes) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def delete_kek(self, session: ISession, tenant_id: typing.Any) -> None:
        raise NotImplementedError

    @abstractmethod
    async def setup(self, session: ISession) -> None:
        raise NotImplementedError

    @abstractmethod
    async def cleanup(self, session: ISession) -> None:
        raise NotImplementedError
