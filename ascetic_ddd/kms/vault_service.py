import base64
import typing
from urllib.parse import quote

import aiohttp

from ascetic_ddd.kms.exceptions import KekNotFound
from ascetic_ddd.kms.interfaces import IKeyManagementService
from ascetic_ddd.session.interfaces import ISession

__all__ = ("VaultTransitService",)


class VaultTransitService(IKeyManagementService):
    """IKeyManagementService adapter for HashiCorp Vault Transit Engine.

    Uses aiohttp for native async HTTP with connection pooling.

    Vault Transit manages the full key lifecycle: key creation, rotation,
    encryption, decryption, and rewrap -- all without exposing plaintext
    keys outside the Vault boundary.

    encrypted_dek format: Vault ciphertext string stored as UTF-8 bytes,
    e.g. b"vault:v1:base64data...". This format is opaque to the caller
    and understood only by Vault.

    Usage::

        import os
        import aiohttp
        from ascetic_ddd.kms.vault_service import VaultTransitService

        async with aiohttp.ClientSession() as http_session:
            kms = VaultTransitService(
                http_session=http_session,
                vault_addr=os.environ["VAULT_ADDR"],
                vault_token=os.environ["VAULT_TOKEN"],
            )
    """

    def __init__(
            self,
            http_session: aiohttp.ClientSession,
            vault_addr: str,
            vault_token: str,
            mount: str = "transit",
            key_type: str = "aes256-gcm96",
    ) -> None:
        self._http_session = http_session
        self._vault_addr = vault_addr.rstrip("/")
        self._vault_token = vault_token
        self._mount = mount
        self._key_type = key_type

    async def encrypt_dek(self, session: ISession, tenant_id: typing.Any, dek: bytes) -> bytes:
        await self._ensure_key(tenant_id)
        result = await self._request(
            "POST", "/encrypt/%s" % self._key_name(tenant_id),
            {"plaintext": base64.b64encode(dek).decode("ascii")},
        )
        return result["data"]["ciphertext"].encode("utf-8")

    async def decrypt_dek(self, session: ISession, tenant_id: typing.Any, encrypted_dek: bytes) -> bytes:
        result = await self._request(
            "POST", "/decrypt/%s" % self._key_name(tenant_id),
            {"ciphertext": encrypted_dek.decode("utf-8")},
        )
        return base64.b64decode(result["data"]["plaintext"])

    async def generate_dek(self, session: ISession, tenant_id: typing.Any) -> tuple[bytes, bytes]:
        await self._ensure_key(tenant_id)
        result = await self._request(
            "POST", "/datakey/plaintext/%s" % self._key_name(tenant_id),
            {"bits": 256},
        )
        plaintext_dek = base64.b64decode(result["data"]["plaintext"])
        encrypted_dek = result["data"]["ciphertext"].encode("utf-8")
        return plaintext_dek, encrypted_dek

    async def rotate_kek(self, session: ISession, tenant_id: typing.Any) -> int:
        key_name = self._key_name(tenant_id)
        if not await self._key_exists(tenant_id):
            await self._request(
                "POST", "/keys/%s" % key_name,
                {"type": self._key_type},
            )
            return 1
        await self._request("POST", "/keys/%s/rotate" % key_name, {})
        result = await self._request("GET", "/keys/%s" % key_name)
        return result["data"]["latest_version"]

    async def rewrap_dek(self, session: ISession, tenant_id: typing.Any, encrypted_dek: bytes) -> bytes:
        result = await self._request(
            "POST", "/rewrap/%s" % self._key_name(tenant_id),
            {"ciphertext": encrypted_dek.decode("utf-8")},
        )
        return result["data"]["ciphertext"].encode("utf-8")

    async def delete_kek(self, session: ISession, tenant_id: typing.Any) -> None:
        key_name = self._key_name(tenant_id)
        try:
            await self._request(
                "POST", "/keys/%s/config" % key_name,
                {"deletion_allowed": True},
            )
            await self._request("DELETE", "/keys/%s" % key_name)
        except KekNotFound:
            pass

    async def setup(self, session: ISession) -> None:
        pass

    async def cleanup(self, session: ISession) -> None:
        pass

    def _key_name(self, tenant_id: typing.Any) -> str:
        return quote(str(tenant_id), safe="")

    async def _key_exists(self, tenant_id: typing.Any) -> bool:
        try:
            await self._request("GET", "/keys/%s" % self._key_name(tenant_id))
            return True
        except KekNotFound:
            return False

    async def _ensure_key(self, tenant_id: typing.Any) -> None:
        """Create key if it doesn't exist. Vault's POST /keys/:name is idempotent."""
        await self._request(
            "POST", "/keys/%s" % self._key_name(tenant_id),
            {"type": self._key_type},
        )

    async def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        url = "%s/v1/%s%s" % (self._vault_addr, self._mount, path)
        headers = {"X-Vault-Token": self._vault_token}
        kwargs = {"headers": headers}
        if data is not None:
            kwargs["json"] = data
        async with self._http_session.request(method, url, **kwargs) as response:
            if response.status == 404:
                raise KekNotFound(path)
            response.raise_for_status()
            if response.status == 204:
                return {}
            return await response.json()
