# Transactional Outbox Pattern

PostgreSQL implementation of the Transactional Outbox pattern for reliable message publishing.

## The Problem: Dual-Write

When a business operation needs to both update the database and publish messages to external systems (message brokers, other services), you cannot guarantee atomicity with traditional approaches:

```python
# DANGEROUS: Not atomic!
await repository.save(order)      # 1. Save to database
await broker.publish(event)       # 2. Publish to message broker
                                  # If crash happens here, message is lost
```

If the application crashes between steps 1 and 2, the database is updated but the message is never published.

## The Solution: Outbox Pattern

Instead of publishing directly, save the message to an `outbox` table within the **same database transaction** as the business state change:

```python
async with session.atomic():
    await repository.save(order)
    await outbox.publish(session, OutboxMessage(
        event_type="OrderCreated",
        payload={"order_id": str(order.id), "amount": order.amount},
        metadata={"event_id": str(uuid4())},
    ))
# Both are committed atomically - or neither
```

A separate dispatcher process reads unpublished messages and sends them to external systems.

## Key Concepts

### 1. Transactional Guarantee

Messages are saved to the Outbox table within the **same database transaction** as business state changes. This ensures that either both the state change AND the message are persisted, or neither is.

### 2. At-Least-Once Delivery

The dispatcher reads unpublished messages and sends them to external systems. If the dispatcher crashes after publishing but before marking as processed, the message will be resent. **Consumers MUST be idempotent**.

### 3. Ordering with transaction_id (xid8)

PostgreSQL's `SERIAL`/`BIGSERIAL` doesn't guarantee ordering in concurrent transactions:

```
TX1: gets position=1, takes 5 seconds
TX2: gets position=2, commits immediately
```

A consumer reading `position > 0` would see message 2 but miss message 1 (still in-flight).

**Solution**: Use `transaction_id` (PostgreSQL `xid8` type) + `position` for ordering:

- `transaction_id` = `pg_current_xact_id()` captures the transaction ID
- Read only messages where `transaction_id < pg_snapshot_xmin(pg_current_snapshot())` (only from COMMITTED transactions visible to all)
- Order by `(transaction_id, position)` for deterministic ordering

### 4. Consumer Groups

Multiple consumers can independently track their position in the outbox. Each consumer group maintains its own `(last_processed_transaction_id, offset_acked)`.

### 5. Visibility Rule

`transaction_id < pg_snapshot_xmin(pg_current_snapshot())` ensures we only read messages from transactions that are fully committed and visible to all sessions.

## Installation

```python
from ascetic_ddd.outbox import Outbox, OutboxMessage
```

## Usage

### Setup

```python
from ascetic_ddd.outbox import Outbox

outbox = Outbox(
    session_pool=pool,
    outbox_table='outbox',         # default
    offsets_table='outbox_offsets', # default
    batch_size=100                  # default
)

# Create tables
await outbox.setup()
```

### Publishing Messages

```python
from ascetic_ddd.outbox import OutboxMessage
from uuid import uuid4

async with session.atomic():
    # Business logic
    await repository.save(order)

    # Publish to outbox (same transaction)
    await outbox.publish(session, OutboxMessage(
        event_type="OrderCreated",
        event_version=1,
        payload={
            "order_id": str(order.id),
            "customer_id": str(order.customer_id),
            "amount": order.amount,
        },
        metadata={
            "event_id": str(uuid4()),  # Required for idempotency
            "correlation_id": correlation_id,
            "causation_id": causation_id,
        },
    ))
```

### Dispatching Messages

#### Option 1: dispatch() - Single Batch

```python
async def send_to_broker(message: OutboxMessage) -> None:
    await broker.publish(
        topic=message.event_type,
        payload=message.payload,
        headers=message.metadata,
    )

# Process one batch
has_messages = await outbox.dispatch(send_to_broker, consumer_group="broker")
```

#### Option 2: run() - Continuous with Workers

```python
# Run continuously with 3 workers
await outbox.run(
    subscriber=send_to_broker,
    consumer_group="broker",
    workers=3,
    poll_interval=1.0,
)
```

#### Option 3: Async Iterator

```python
async for message in outbox:
    await send_to_broker(message)
    # Position is updated after yield returns
```

### Position Management

```python
# Get current position
tx_id, offset = await outbox.get_position(session, "broker")

# Reset position (reprocess from beginning)
await outbox.set_position(session, "broker", transaction_id=0, offset=0)

# Skip ahead
await outbox.set_position(session, "broker", transaction_id=1000, offset=50)
```

## Schema

The `setup()` method creates:

### outbox table

```sql
CREATE TABLE outbox (
    "position" BIGSERIAL,
    "event_type" VARCHAR(255) NOT NULL,
    "event_version" SMALLINT NOT NULL DEFAULT 1,
    "payload" JSONB NOT NULL,
    "metadata" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "transaction_id" xid8 NOT NULL,
    PRIMARY KEY ("transaction_id", "position")
);

CREATE INDEX outbox_position_idx ON outbox ("position");
CREATE INDEX outbox_event_type_idx ON outbox ("event_type");
CREATE UNIQUE INDEX outbox_event_id_uniq ON outbox (((metadata->>'event_id')::uuid));
```

### outbox_offsets table

```sql
CREATE TABLE outbox_offsets (
    "consumer_group" VARCHAR(255) NOT NULL,
    "offset_acked" BIGINT NOT NULL DEFAULT 0,
    "last_processed_transaction_id" xid8 NOT NULL DEFAULT '0',
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY ("consumer_group")
);
```

## Considerations

### Duplicate Delivery

Consumers must handle duplicates. Use `metadata.event_id` for deduplication:

```python
async def handle_message(message: OutboxMessage) -> None:
    event_id = message.metadata.get("event_id")
    if await is_already_processed(event_id):
        return  # Skip duplicate

    await process(message)
    await mark_as_processed(event_id)
```

### Message Ordering

- Within a single transaction: ordered by `position`
- Across transactions: ordered by `transaction_id`

### Table Growth

Processed messages should be archived or deleted periodically:

```sql
DELETE FROM outbox
WHERE transaction_id < (
    SELECT MIN(last_processed_transaction_id)
    FROM outbox_offsets
)
AND created_at < NOW() - INTERVAL '7 days';
```

### Polling vs Push

This implementation uses polling. For lower latency, consider:
- PostgreSQL `LISTEN`/`NOTIFY`
- `pg_logical` replication

## API Reference

### OutboxMessage

```python
@dataclass
class OutboxMessage:
    event_type: str              # Event type (e.g., 'OrderCreated')
    payload: dict[str, Any]      # Message payload
    metadata: dict[str, Any]     # Must contain 'event_id' for idempotency
    event_version: int = 1       # Schema version
    created_at: str | None       # Auto-assigned by DB
    position: int | None         # Auto-assigned by DB
    transaction_id: int | None   # Auto-assigned by pg_current_xact_id()
```

### IOutbox Interface

| Method | Description |
|--------|-------------|
| `publish(session, message)` | Store message in outbox within current transaction |
| `dispatch(subscriber, consumer_group)` | Dispatch next batch of messages |
| `run(subscriber, consumer_group, workers, poll_interval)` | Run continuous dispatching |
| `__aiter__()` | Async iterator for message streaming |
| `get_position(session, consumer_group)` | Get current position for consumer group |
| `set_position(session, consumer_group, transaction_id, offset)` | Set position for consumer group |
| `setup()` | Create tables and indexes |
| `cleanup()` | Cleanup resources |

### ISubscriber

```python
ISubscriber: TypeAlias = Callable[[OutboxMessage], Awaitable[None]]
```

## References

- [The Outbox Pattern](https://www.kamilgrzybek.com/blog/posts/the-outbox-pattern) by Kamil Grzybek
- [Handling Domain Event: Missing Part](https://www.kamilgrzybek.com/blog/posts/handling-domain-event-missing-part) by Kamil Grzybek
- [Ordering in Postgres Outbox](https://event-driven.io/en/ordering_in_postgres_outbox/) by Oskar Dudycz
- [Outbox, Inbox patterns and delivery guarantees explained](https://event-driven.io/en/outbox_inbox_patterns_and_delivery_guarantees_explained/) by Oskar Dudycz
