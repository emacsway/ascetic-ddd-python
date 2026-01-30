"""Inbox pattern for idempotent message processing with causal consistency.

The Inbox pattern ensures:
- **Idempotency**: Duplicate messages are ignored (same PK = same message)
- **Causal Consistency**: Messages are processed only after their causal dependencies
- **At-least-once delivery**: Messages are stored before processing

Usage:
    from ascetic_ddd.inbox import Inbox, InboxMessage

    class MyInbox(Inbox):
        async def do_handle(self, session, message):
            # Handle message directly or dispatch to external handler
            event = deserialize_event(message.event_type, message.payload)
            await handle_event(session, event)

    inbox = MyInbox(session_pool)
    await inbox.setup()

    # Receive messages from external source (e.g., message broker)
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

    # Process messages (call periodically or on notification)
    while await inbox.handle():
        pass
"""

from ascetic_ddd.inbox.inbox import Inbox
from ascetic_ddd.inbox.interfaces import IInbox
from ascetic_ddd.inbox.message import InboxMessage


__all__ = (
    'IInbox',
    'Inbox',
    'InboxMessage',
)
