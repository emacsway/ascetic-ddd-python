# DekStore

```{index} pair: seedwork; DEK store
```
```{index} pair: seedwork; encryption
```

The `DekStore` manages Data Encryption Keys (DEKs) per event stream.
Each aggregate instance (identified by `StreamId`) gets its own DEK,
providing fine-grained encryption isolation.

DEKs are **versioned** -- each stream can have multiple DEK versions
(e.g. after algorithm migration). The version is embedded as a 4-byte
prefix in the encrypted payload, allowing the read path to select the
correct cipher for decryption.

```python
class IDekStore(metaclass=ABCMeta):

    async def get_or_create(self, session, stream_id: StreamId) -> ICipher
    async def get(self, session, stream_id: StreamId, key_version: int) -> ICipher
    async def get_all(self, session, stream_id: StreamId) -> ICipher
    async def delete(self, session, stream_id: StreamId) -> None
    async def rewrap(self, session, tenant_id) -> int
```

- `get_or_create` -- used on the write path. Returns `ICipher` for the
  latest DEK version, creating a new DEK (version 1) if none exists.
  The cipher prepends the version prefix on `encrypt()`.
- `get` -- returns `ICipher` for a specific DEK version. Used when the
  version is already known (e.g. extracted from an event payload).
  Raises `DekNotFound` if no DEK exists for the given version.
- `get_all` -- returns a composite `ICipher` that handles all DEK
  versions for a stream. `encrypt()` uses the latest version,
  `decrypt()` dispatches by the version prefix in the ciphertext.
  Used on the read path when loading multiple events that may span
  different DEK versions.
- `delete` -- removes all DEK versions for a stream.
- `rewrap` -- re-encrypts all DEKs for a tenant with the current KEK
  version (after `rotate_kek`). Does not change the DEK algorithm.
  Returns the number of re-wrapped DEKs.

DEKs are stored encrypted in the `stream_deks` table. Decryption
requires the tenant's KEK from the [KMS module](../../../kms/index.rst).

See [ADR-0009: Envelope Encryption](../../../../adr/0009-envelope-encryption.rst) for the architectural decision.

`tenant_id` is typed as `typing.Any` -- the actual type is determined
by the user's DDL schema (`varchar`, `integer`, etc.). The DDL
can include `REFERENCES` to enforce referential integrity.

## DEK versioning

Each DEK version is stored as a separate row in `stream_deks`, with
its own `algorithm`. The encrypted event payload starts with a 4-byte
version prefix identifying which DEK was used:

```
[4 bytes version][12 bytes nonce][ciphertext][16 bytes tag]
```

This enables safe algorithm migration: new events are encrypted with
the latest DEK version (and its algorithm), while old events remain
decryptable with their original DEK version.

## Codec

```{index} pair: seedwork; codec
```
```{index} pair: seedwork; AES-256-GCM
```

The `ICodec` interface provides composable encode/decode transformations
for event payloads using the Decorator pattern:

```python
cipher = await dek_store.get_or_create(session, stream_id)
EncryptionCodec(cipher, ZlibCodec(JsonCodec()))
```

- `JsonCodec` -- serializes `dict` to JSON bytes and back
- `ZlibCodec` -- compresses/decompresses bytes
- `EncryptionCodec` -- encrypts/decrypts using any `ICipher` implementation.
  Wraps the cipher as a codec decorator.
- `DekStore` constructs the cipher internally (`Aes256GcmCipher` with
  AAD derived from `stream_id`), dispatching by the `algorithm` column.
