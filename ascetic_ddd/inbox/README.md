# Inbox Pattern

Inbox pattern for idempotent message processing with causal consistency.

## Features

- **Idempotency**: Duplicate messages are ignored (same PK = same message)
- **Causal Consistency**: Messages are processed only after their causal dependencies
- **At-least-once delivery**: Messages are stored before processing

## Usage

```python
from ascetic_ddd.inbox import Inbox, InboxMessage

inbox = Inbox(session_pool)
await inbox.setup()
```

### Publishing Messages

Receive messages from external source (e.g., message broker):

```python
await inbox.publish(InboxMessage(
    tenant_id="tenant1",
    stream_type="Order",
    stream_id={"id": "order-123"},
    stream_position=1,
    event_type="OrderCreated",
    event_version=1,
    payload={"amount": 100},
    metadata={
        "event_id": "uuid-123",
        "causal_dependencies": [
            {"tenant_id": "tenant1", "stream_type": "User", "stream_id": {"id": "user-1"}, "stream_position": 5}
        ]
    }
))
```

### Processing Messages

Two approaches are available:

#### 1. Subscription-based (Decorator)

Register handlers for specific event types:

```python
class MyInbox(Inbox):
    pass

inbox = MyInbox(session_pool)

@inbox.subscribe("OrderCreated", event_version=1)
async def handle_order_created(session, message):
    order = deserialize(message.payload)
    await process_order(session, order)

@inbox.subscribe("OrderShipped", event_version=1)
async def handle_order_shipped(session, message):
    await notify_customer(session, message.payload)

# Process messages (call periodically or on notification)
while await inbox.dispatch():
    pass
```

#### 2. Iterator-based (Async for)

Process messages in an infinite loop (like Kafka consumer):

```python
async for session, message in inbox:
    # Process message within transaction
    event = deserialize_event(message.event_type, message.payload)
    await handle_event(session, event)
    # Message is automatically marked as processed after yield
```

The iterator:
- Runs indefinitely, polling for new messages
- Yields `(session, message)` tuples within a transaction
- Marks messages as processed after the yield returns
- Use `Ctrl+C` or `break` to stop

#### 3. Concurrent Processing (run)

Run multiple workers for parallel message processing:

```python
# Single worker (default)
await inbox.run()

# Multiple concurrent workers
await inbox.run(workers=4, poll_interval=0.5)
```

Uses `FOR UPDATE SKIP LOCKED` to prevent multiple workers from processing the same message.

### Custom Handler (Override)

Override `do_handle` for custom processing logic:

```python
class MyInbox(Inbox):
    async def do_handle(self, session, message):
        # Dispatch to mediator, event bus, or handle directly
        event = deserialize_event(message.event_type, message.payload)
        await self.mediator.send(session, event)
```

## Causal Dependencies

Messages can declare dependencies on other messages. A message is only processed after all its dependencies have been processed:

```python
metadata={
    "causal_dependencies": [
        {
            "tenant_id": "tenant1",
            "stream_type": "User",
            "stream_id": {"id": "user-1"},
            "stream_position": 5
        }
    ]
}
```

If dependencies are not satisfied, the Inbox skips to the next message and retries later.

## Database Schema

The Inbox uses PostgreSQL with the following schema:

```sql
CREATE SEQUENCE inbox_received_position_seq;

CREATE TABLE inbox (
    tenant_id varchar(128) NOT NULL,
    stream_type varchar(128) NOT NULL,
    stream_id jsonb NOT NULL,
    stream_position integer NOT NULL,
    event_type varchar(60) NOT NULL,
    event_version smallint NOT NULL,
    payload jsonb NOT NULL,
    metadata jsonb NULL,
    received_position bigint NOT NULL UNIQUE DEFAULT nextval('inbox_received_position_seq'),
    processed_position bigint NULL,
    CONSTRAINT inbox_pk PRIMARY KEY (tenant_id, stream_type, stream_id, stream_position)
);
```

- **Primary Key**: `(tenant_id, stream_type, stream_id, stream_position)` ensures idempotency
- **received_position**: Order of message arrival
- **processed_position**: Set when message is processed (NULL = unprocessed)
