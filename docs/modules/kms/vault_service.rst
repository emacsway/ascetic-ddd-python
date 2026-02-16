VaultTransitService
===================

.. index:: KMS, Vault, HashiCorp Vault, Transit Engine

The ``VaultTransitService`` is an ``IKeyManagementService`` adapter for
`HashiCorp Vault Transit Engine <https://developer.hashicorp.com/vault/docs/secrets/transit>`__.

Vault Transit manages the full key lifecycle -- key creation, rotation,
encryption, decryption, and rewrap -- all without exposing plaintext
keys outside the Vault boundary.

Unlike ``PgKeyManagementService``, which stores KEKs in PostgreSQL
encrypted with a master key, ``VaultTransitService`` delegates all
cryptographic operations to Vault. The application never sees
plaintext KEKs.

Usage
-----

.. code-block:: python

   import os
   from ascetic_ddd.kms.vault_service import VaultTransitService
   from ascetic_ddd.session.rest_session import RestSessionPool

   kms = VaultTransitService(
       vault_addr=os.environ["VAULT_ADDR"],
       vault_token=os.environ["VAULT_TOKEN"],
   )
   session_pool = RestSessionPool()

   async with session_pool.session() as session:
       async with session.atomic() as tx_session:
           dek, encrypted_dek = await kms.generate_dek(tx_session, tenant_id)

The ``VaultTransitService`` extracts ``aiohttp.ClientSession`` from
``ISession`` via ``extract_request`` -- the same pattern used by
``PgKeyManagementService`` with ``extract_connection``. The HTTP session
lifecycle is managed by ``RestSessionPool``.

Constructor parameters
^^^^^^^^^^^^^^^^^^^^^^

``vault_addr``
    Vault server address (e.g. ``https://vault.example.com:8200``).

``vault_token``
    Vault authentication token.

``mount``
    Transit secrets engine mount path (default: ``transit``).

``key_type``
    Key type for new keys (default: ``aes256-gcm96``).

encrypted_dek format
^^^^^^^^^^^^^^^^^^^^

The ``encrypted_dek`` returned by Vault is a ciphertext string stored
as UTF-8 bytes, e.g. ``b"vault:v1:base64data..."``. This format is
opaque to the caller and understood only by Vault. Unlike
``PgKeyManagementService`` (which uses a ``key_version + nonce +
ciphertext`` binary format), Vault ciphertext already embeds the key
version.

Testing
-------

Integration tests require a running Vault instance with Transit
engine enabled. Use Docker Compose:

.. code-block:: bash

   docker compose up -d vault
   python -m unittest ascetic_ddd.kms.tests.integration.test_vault_service -v

Environment variables (in ``config/.env``):

.. code-block:: bash

   TEST_VAULT_ADDR='http://localhost:8200'
   TEST_VAULT_TOKEN='test-root-token'

See ``docker-compose.yml`` for the Vault service configuration.
