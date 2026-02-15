# DekStore

```{index} pair: seedwork; DEK store
```
```{index} pair: seedwork; encryption
```

The `DekStore` manages Data Encryption Keys (DEKs) per event stream.
Each aggregate instance (identified by `StreamId`) gets its own DEK,
providing fine-grained encryption isolation.

```python
class IDekStore(metaclass=ABCMeta):

    async def get_or_create(self, session, stream_id: StreamId) -> bytes
    async def get(self, session, stream_id: StreamId) -> bytes
    async def delete(self, session, stream_id: StreamId) -> None
    async def rewrap(self, session, tenant_id) -> int
```

- `get_or_create` -- used on the write path. Returns the existing DEK
  or generates a new one via KMS and stores the encrypted form.
- `get` -- used on the read path. Raises `KeyError` if no DEK exists.
- `delete` -- removes the DEK for a stream.
- `rewrap` -- re-encrypts all DEKs for a tenant with the current KEK
  version (after `rotate_kek`). Returns the number of re-wrapped DEKs.

DEKs are stored encrypted in the `stream_deks` table. Decryption
requires the tenant's KEK from the [KMS module](../../../kms/index.rst).

See [ADR-0009: Envelope Encryption](../../../../adr/0009-envelope-encryption.rst) for the architectural decision.

## Codec

```{index} pair: seedwork; codec
```
```{index} pair: seedwork; AES-256-GCM
```

The `ICodec` interface provides composable encode/decode transformations
for event payloads using the Decorator pattern:

```python
AesGcmEncryptor(dek, ZlibCompressor(JsonCodec()))
```

- `JsonCodec` -- serializes `dict` to JSON bytes and back
- `ZlibCompressor` -- compresses/decompresses bytes
- `AesGcmEncryptor` -- encrypts/decrypts with AES-256-GCM
