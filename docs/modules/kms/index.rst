KMS
===

.. index:: KMS, Key Management Service, KEK, envelope encryption

The ``ascetic_ddd.kms`` module provides a Key Management Service for
envelope encryption in multi-tenant systems.

Overview
--------

The module manages Key Encryption Keys (KEKs) -- per-tenant symmetric keys
used to encrypt and decrypt Data Encryption Keys (DEKs). KEKs are stored
in PostgreSQL, encrypted with a master key.

The architecture follows the
`Vault Transit Engine <https://developer.hashicorp.com/vault/docs/secrets/transit>`__
model: the KMS never exposes plaintext KEKs outside its boundary.

See :doc:`/adr/0009-envelope-encryption` for the architectural decision.

Interface
---------

.. code-block:: python

   class IKeyManagementService(metaclass=ABCMeta):

       async def encrypt_dek(self, session, tenant_id, dek: bytes) -> bytes
       async def decrypt_dek(self, session, tenant_id, encrypted_dek: bytes) -> bytes
       async def generate_dek(self, session, tenant_id) -> tuple[bytes, bytes]
       async def rotate_kek(self, session, tenant_id) -> int
       async def rewrap_dek(self, session, tenant_id, encrypted_dek: bytes) -> bytes
       async def delete_kek(self, session, tenant_id) -> None
       async def setup(self, session) -> None
       async def cleanup(self, session) -> None

``tenant_id`` is typed as ``typing.Any`` -- the actual type is determined
by the user's DDL schema (``varchar``, ``integer``, etc.). The DDL
can include ``REFERENCES`` to enforce referential integrity.

Methods
^^^^^^^

``encrypt_dek(session, tenant_id, dek)``
    Encrypts a plaintext DEK with the current KEK version.
    If no KEK exists for the tenant, one is created automatically.
    Returns ``key_version (4 bytes) + nonce (12 bytes) + ciphertext``.

``decrypt_dek(session, tenant_id, encrypted_dek)``
    Decrypts a DEK. Extracts the key version from the first 4 bytes
    to locate the correct KEK version. Raises ``KekDoesNotExist``
    if no KEK is found for the tenant/version.

``generate_dek(session, tenant_id)``
    Generates a new AES-256 DEK and returns ``(plaintext_dek, encrypted_dek)``.

``rotate_kek(session, tenant_id)``
    Creates a new KEK version for the tenant. Returns the new version number.
    Old KEK versions are preserved for decrypting existing DEKs.

``rewrap_dek(session, tenant_id, encrypted_dek)``
    Re-encrypts a DEK with the current (latest) KEK version.
    Used after KEK rotation to migrate DEKs to the new key version.

``delete_kek(session, tenant_id)``
    Deletes all KEK versions for a tenant. This is the crypto-shredding
    operation: all DEKs encrypted with these KEKs become permanently
    undecryptable.

Implementation: PgKeyManagementService
---------------------------------------

.. code-block:: python

   from ascetic_ddd.kms.kms import PgKeyManagementService

   master_key = AESGCM.generate_key(bit_length=256)
   kms = PgKeyManagementService(master_key)

The ``master_key`` is a 256-bit AES key, typically loaded from
an environment variable or secret manager. It encrypts KEKs at rest
in the ``kms_keys`` table.

Schema:

.. code-block:: sql

   CREATE TABLE kms_keys (
       tenant_id varchar(128) NOT NULL,
       key_version integer NOT NULL,
       encrypted_kek bytea NOT NULL,
       created_at timestamptz NOT NULL DEFAULT now(),
       CONSTRAINT kms_keys_pk PRIMARY KEY (tenant_id, key_version)
   );

The table name is configurable via the ``_table`` class attribute.

Encrypted KEK format: ``nonce (12 bytes) + AES-256-GCM ciphertext``.

Key hierarchy
-------------

::

  Master Key (env var / secret manager)
       │
       └─ encrypts ─→ KEK per tenant (kms_keys table)
                           │
                           └─ encrypts ─→ DEK per stream (stream_deks table)
                                               │
                                               └─ encrypts ─→ event payload

Crypto-shredding
----------------

To render all data for a tenant permanently irrecoverable:

.. code-block:: python

   await kms.delete_kek(session, tenant_id)

This deletes all KEK versions. Any subsequent attempt to decrypt
the tenant's DEKs will fail, making all their event payloads
unreadable -- without physically deleting events from the
immutable event log.
