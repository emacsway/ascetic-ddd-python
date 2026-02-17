ADR-0009: Envelope Encryption for Event Store
==============================================

.. index:: ADR; envelope encryption, KMS, DEK, KEK, AES-256-GCM, crypto-shredding, GDPR

Status
------
Accepted

Context
-------

In a multi-tenant event sourcing system, event payloads may contain
personally identifiable information (PII), financial data, and other
sensitive business data. Several requirements drive the need for
field-level encryption:

1. **Data isolation between tenants** -- compromise of one tenant's
   encryption key must not affect other tenants.
2. **GDPR right to erasure** -- the system must support the ability
   to render a tenant's data irrecoverable without physically deleting
   immutable events (crypto-shredding).
3. **Key rotation** -- encryption keys must be rotatable without
   re-encrypting the entire event store.
4. **Performance** -- encryption/decryption should not become
   a bottleneck on the write or read path.

The standard industry approach to these requirements is
`Envelope Encryption <https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html#enveloping>`__,
used by AWS KMS, HashiCorp Vault Transit, GCP KMS, and Azure Key Vault.

See also:

- `Envelope encryption (Google Cloud KMS) <https://docs.cloud.google.com/kms/docs/envelope-encryption>`__
- `About data encryption (AWS) <https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-data-at-rest-encryption/about-data-encryption.html>`__
- `KMS wrapping libraries split out from Vault <https://github.com/hashicorp/go-kms-wrapping>`__
- `Eventsourcing Patterns: Crypto-Shredding <https://verraes.net/2019/05/eventsourcing-patterns-throw-away-the-key/>`__
- `Eventsourcing Patterns: Forgettable Payloads <https://verraes.net/2019/05/eventsourcing-patterns-forgettable-payloads/>`__


Envelope Encryption
^^^^^^^^^^^^^^^^^^^

The core idea is a two-level key hierarchy:

- **Data Encryption Key (DEK)** -- a symmetric key (AES-256) used to
  encrypt event payloads. Generated per-stream (per-aggregate instance).
  Stored alongside the data in encrypted form.
- **Key Encryption Key (KEK)** -- a per-tenant key used to encrypt/decrypt
  DEKs. Managed by the Key Management Service (KMS). Never leaves the KMS
  in plaintext.

::

  Application                              KMS
  ┌─────────────────────────────┐     ┌──────────────────────────┐
  │ EventStore                  │     │ kms_keys                 │
  │  ├─ event_log               │     │  ├─ tenant_id            │
  │  │   ├─ payload (bytea)     │     │  ├─ key_version          │
  │  │   └─ metadata (jsonb)    │     │  ├─ encrypted_key        │
  │  └─ stream_deks             │     │  ├─ master_algorithm     │
  │      ├─ stream_id           │     │  └─ key_algorithm        │
  │      ├─ version             │     └──────────────────────────┘
  │      ├─ encrypted_dek       │
  │      └─ algorithm           │
  └─────────────────────────────┘

Key rotation requires re-encrypting only the DEKs (few per tenant),
not the events themselves (potentially millions).


What to encrypt
^^^^^^^^^^^^^^^

- **Encrypt**: ``payload`` -- business data containing PII, financial
  information, etc.
- **Do not encrypt**: ``metadata`` (contains ``event_id`` used in unique
  index, correlation/causation IDs for routing), ``event_type``,
  ``stream_id``, ``stream_position``, ``event_version`` -- needed by
  projections and subscriptions for filtering and routing.


Algorithm
^^^^^^^^^

**AES-256-GCM** was chosen as the encryption algorithm:

- **Authenticated encryption** -- GCM provides both confidentiality and
  integrity (tamper detection). This is critical for an immutable event
  store.
- **Hardware acceleration** -- AES-NI is available on all modern server
  CPUs. The ``cryptography`` library uses it automatically.
- **Industry standard** -- AWS KMS, Vault Transit, GCP KMS all use
  AES-256-GCM by default.
- **Nonce safety** -- with a random 12-byte nonce, the collision limit
  is ~2\ :sup:`32` encryptions per DEK. With per-stream DEK granularity,
  this is not a practical concern.
- **AAD (Associated Authenticated Data)** -- ``tenant_id`` is used as
  AAD at all encryption levels (master key → KEK, KEK → DEK).
  This cryptographically binds ciphertext to its tenant, preventing
  cross-tenant ciphertext substitution even with direct DB write access.
  The domain model (``BaseKey``) applies AAD uniformly via ``_aad``
  property derived from ``tenant_id``.


KMS interface
^^^^^^^^^^^^^

The ``IKeyManagementService`` interface mirrors the
`Vault Transit Engine <https://developer.hashicorp.com/vault/docs/secrets/transit>`__
API surface:

- ``encrypt_dek`` / ``decrypt_dek`` -- envelope operations
- ``generate_dek`` -- generate a new DEK and return both plaintext
  and encrypted forms
- ``rotate_kek`` -- create a new KEK version for a tenant
- ``rewrap_dek`` -- re-encrypt a DEK with the current KEK version
  (after rotation)
- ``delete_kek`` -- delete all KEK versions for a tenant
  (crypto-shredding)

Two implementations are provided: ``PgKeyManagementService`` stores
KEKs in PostgreSQL (encrypted with a master key from an environment
variable), ``VaultTransitService`` delegates all cryptographic
operations to HashiCorp Vault Transit. The interface allows adding
other backends (AWS KMS, GCP KMS) without changing the EventStore code.


DEK granularity
^^^^^^^^^^^^^^^

DEKs are generated **per-stream** (per-aggregate instance), identified
by ``StreamId(tenant_id, stream_type, stream_id)``. Each stream can
have multiple **versioned** DEKs (for algorithm migration). This provides:

- Better isolation than per-tenant (compromise of one DEK only affects
  one aggregate instance)
- Manageable number of keys (one per aggregate instance, not per event)
- Natural boundary for crypto-shredding at stream level
- Safe algorithm migration without re-encrypting existing events


Alternatives considered
^^^^^^^^^^^^^^^^^^^^^^^

**PostgreSQL pgcrypto (column-level encryption)**

PostgreSQL's ``pgcrypto`` extension can encrypt individual columns
using ``pgp_sym_encrypt`` / ``pgp_sym_decrypt``. The per-tenant key
is passed via ``SET LOCAL`` session variable:

.. code-block:: sql

   BEGIN;
   SET LOCAL app.tenant_key = 'per-tenant-secret';
   INSERT INTO events (payload)
   VALUES (pgp_sym_encrypt('{"amount": 100}', current_setting('app.tenant_key')));
   COMMIT;

This was rejected for several reasons:

1. **Key management stays in the application anyway.** PostgreSQL does
   not manage keys -- the entire KEK/DEK hierarchy, rotation, and
   caching still has to live in application code. ``pgcrypto`` only
   moves the ``AES_ENCRYPT`` call from the application to SQL.

2. **Performance.** Decryption runs on the database server CPU. During
   projection rebuild or catch-up subscriptions, decrypting thousands
   of events loads PostgreSQL instead of horizontally scalable
   read-side services. In CQRS the heavy work should be on subscribers.

3. **Logging and leaks.** ``pg_stat_statements``, slow query log, and
   ``EXPLAIN ANALYZE`` may capture decrypted values or keys. Requires
   careful tuning of ``log_min_duration_statement`` and disabling
   parameter logging.

4. **No crypto-shredding guarantee.** After deleting a tenant's key,
   remnants may persist in PostgreSQL logs, ``pg_stat``, or WAL.

5. **Backup exposure.** ``pg_dump`` exports encrypted blobs (good), but
   if keys are stored in the same database or passed via session
   variables that get logged, the protection is illusory.

PostgreSQL-level encryption may be appropriate for prototypes or when
a full KMS is overkill, but for a multi-tenant event sourcing system
with crypto-shredding requirements, application-level envelope
encryption is the correct choice.


Decision
--------

1. **Payload column type changed from** ``jsonb`` **to** ``bytea``.
   Encrypted payload is binary, not JSON. Metadata remains ``jsonb``.

2. **Codec decorator chain** applied to payload on write/read:

   .. code-block:: python

      EncryptionCodec(Aes256GcmCipher(dek, aad), ZlibCodec(JsonCodec()))

   The chain: serialize to JSON bytes, compress with zlib, encrypt with
   AES-256-GCM. On read -- the reverse. The ``ICodec`` interface
   (``encode``/``decode``) allows composing arbitrary transformations
   via the Decorator pattern.

3. **DekStore returns** ``ICipher`` **instead of raw key bytes**.
   ``get_or_create`` and ``get`` return a ready-to-use ``ICipher``
   that handles version prefix and AAD internally. ``get_all`` returns
   a composite cipher that dispatches ``decrypt()`` by the version
   prefix in the ciphertext. The ``EventStore`` no longer knows about
   ``Aes256GcmCipher`` -- cipher construction is encapsulated in
   ``DekStore._make_raw_cipher()``, which dispatches by the
   ``algorithm`` column stored per DEK version.

4. **DEKs are versioned**. Each stream can have multiple DEK versions
   (stored as separate rows in ``stream_deks``). The encrypted payload
   starts with a 4-byte version prefix identifying which DEK was used.
   This enables algorithm migration without re-encrypting existing
   events: new events use the latest DEK version, old events remain
   decryptable with their original version.

5. **Query requests codec via factory, not a ready instance**.
   ``evaluate(codec_factory, session)`` -- the query receives an
   ``ICodecFactory`` (``Callable[[ISession, StreamId], Awaitable[ICodec]]``)
   and calls it with its own ``StreamId``. This way the query -- which
   already owns the stream identity -- decides when to obtain the codec,
   while the EventStore controls how it is constructed:

   .. code-block:: python

      # Write path: get_or_create returns ICipher for latest DEK version
      async def _make_codec_factory(self) -> ICodecFactory:
          _cache = {}

          async def codec_factory(session, stream_id):
              if stream_id not in _cache:
                  cipher = await self._dek_store.get_or_create(session, stream_id)
                  _cache[stream_id] = EncryptionCodec(cipher, ZlibCodec(JsonCodec()))
              return _cache[stream_id]

          return codec_factory

      # Read path: get_all returns composite ICipher for all DEK versions
      async def _make_read_codec_factory(self) -> ICodecFactory:
          _cache = {}

          async def codec_factory(session, stream_id):
              if stream_id not in _cache:
                  cipher = await self._dek_store.get_all(session, stream_id)
                  _cache[stream_id] = EncryptionCodec(cipher, ZlibCodec(JsonCodec()))
              return _cache[stream_id]

          return codec_factory

   ``_save()`` does not need ``stream_id`` as a parameter --
   the responsibility is given to the object that owns the data.
   ``get_or_create`` is used on the write path (creates DEK if absent),
   ``get_all`` on the read path (all DEK versions for a stream).

6. **Codec factory is a dependency, session is an argument**.
   ``evaluate(codec_factory, session)`` -- the factory (strategy) comes
   before the runtime argument. This follows the principle that
   dependencies (stable, suitable for ``functools.partial``) precede
   arguments (varying per call).

7. **KMS and DekStore use dynamic table names** (``%s`` substitution
   for table name, ``%%s`` for query parameters), allowing test
   subclasses to override ``_table`` without duplicating SQL.

8. **tenant_id typed as** ``typing.Any``. The KMS and DekStore do not
   enforce a specific type for ``tenant_id``. The DDL type is chosen
   by the user in their schema (``varchar``, ``integer``, with or
   without ``REFERENCES``). Production code does not apply type
   conversions.


Consequences
------------

- **Encryption at rest for event payloads**: all event payloads are
  stored as encrypted binary. An attacker with database access cannot
  read business data without the master key.

- **Crypto-shredding for GDPR**: deleting a tenant's KEK
  (``delete_kek``) renders all their events permanently unreadable
  without physically deleting rows from the immutable event store.

- **Transparent key rotation**: ``rotate_kek`` creates a new KEK
  version. Old events remain decryptable (DEKs still decrypt with
  their original KEK version). ``rewrap_dek`` can re-encrypt DEKs
  with the new version when needed.

- **Swappable KMS backend**: the ``IKeyManagementService`` interface
  allows replacing ``PgKeyManagementService`` with Vault Transit,
  AWS KMS, or any other backend.

- **Composable codec chain**: ``ICodec`` decorators can be rearranged
  (e.g., remove compression, add signing) without modifying EventStore.

- **Trade-off -- no queryable payload**: since payload is now ``bytea``,
  SQL queries cannot filter or index on payload fields. This is
  acceptable in event sourcing where projections handle query-side
  concerns.

- **Safe algorithm migration**: DEK versioning allows switching to a
  new encryption algorithm without re-encrypting existing events.
  New events use the latest DEK version; old events are decrypted
  with their original version (identified by the 4-byte prefix in
  the payload).

- **Trade-off -- DEK lookup per stream**: each distinct stream requires
  a DEK lookup. The ``ICodecFactory`` closure caches codecs by
  ``StreamId``, so repeated access to the same stream within one
  ``_save()`` / ``evaluate()`` call does not trigger additional lookups.

Related
-------

- :doc:`0008-aggregate-encapsulation` -- Mediator/Exporter pattern used
  to export event state for serialization
