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
  │      ├─ encrypted_dek       │     └──────────────────────────┘
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

The provided ``PgKeyManagementService`` implementation stores KEKs in
PostgreSQL, encrypted with a master key from an environment variable.
This is a pragmatic starting point; the interface allows replacing
it with Vault Transit or AWS KMS without changing the EventStore code.


DEK granularity
^^^^^^^^^^^^^^^

DEKs are generated **per-stream** (per-aggregate instance), identified
by ``StreamId(tenant_id, stream_type, stream_id)``. This provides:

- Better isolation than per-tenant (compromise of one DEK only affects
  one aggregate instance)
- Manageable number of keys (one per aggregate instance, not per event)
- Natural boundary for crypto-shredding at stream level


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

3. **Query requests codec via factory, not a ready instance**.
   ``evaluate(codec_factory, session)`` -- the query receives an
   ``ICodecFactory`` (``Callable[[ISession, StreamId], Awaitable[ICodec]]``)
   and calls it with its own ``StreamId``. This way the query -- which
   already owns the stream identity -- decides when to obtain the codec,
   while the EventStore controls how it is constructed:

   .. code-block:: python

      # EventStore creates the factory with caching closure
      async def _make_codec_factory(self) -> ICodecFactory:
          _cache = {}

          async def codec_factory(session, stream_id):
              if stream_id not in _cache:
                  dek = await self._dek_store.get_or_create(session, stream_id)
                  aad = str(stream_id).encode("utf-8")
                  cipher = Aes256GcmCipher(dek, aad)
                  _cache[stream_id] = EncryptionCodec(cipher, ZlibCodec(JsonCodec()))
              return _cache[stream_id]

          return codec_factory

      # Query calls the factory with its own StreamId
      async def evaluate(self, codec_factory, session):
          codec = await codec_factory(session, StreamId(*self._params[:3]))
          ...

   ``_save()`` does not need ``stream_id`` as a parameter --
   the responsibility is given to the object that owns the data.
   ``get_or_create`` is used on the write path (creates DEK if absent),
   ``get`` on the read path (DEK must already exist).

4. **Codec factory is a dependency, session is an argument**.
   ``evaluate(codec_factory, session)`` -- the factory (strategy) comes
   before the runtime argument. This follows the principle that
   dependencies (stable, suitable for ``functools.partial``) precede
   arguments (varying per call).

5. **KMS and DekStore use dynamic table names** (``%s`` substitution
   for table name, ``%%s`` for query parameters), allowing test
   subclasses to override ``_table`` without duplicating SQL.

6. **tenant_id typed as** ``typing.Any``. The KMS and DekStore do not
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

- **Trade-off -- DEK lookup per stream**: each distinct stream requires
  a DEK lookup. The ``ICodecFactory`` closure caches codecs by
  ``StreamId``, so repeated access to the same stream within one
  ``_save()`` / ``evaluate()`` call does not trigger additional lookups.

Related
-------

- :doc:`0008-aggregate-encapsulation` -- Mediator/Exporter pattern used
  to export event state for serialization
