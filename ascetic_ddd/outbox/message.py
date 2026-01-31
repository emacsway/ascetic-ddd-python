"""Outbox message - structure for outgoing integration messages."""

from dataclasses import dataclass
from typing import Any


__all__ = (
    'OutboxMessage',
)


@dataclass
class OutboxMessage:
    """Outgoing integration message for the Outbox pattern.

    Attributes:
        event_type: Type of the event (e.g., 'OrderCreated').
        event_version: Version of the event schema.
        payload: Message payload (serialized to JSON).
        metadata: Message metadata (must contain 'event_id' for idempotency).
        created_at: Timestamp when message was created (auto-assigned by DB).
        position: Position in the outbox (auto-assigned by DB).
        transaction_id: PostgreSQL transaction ID (auto-assigned by pg_current_xact_id()).
    """
    event_type: str
    payload: dict[str, Any]
    metadata: dict[str, Any]  # Required: must contain 'event_id'
    event_version: int = 1
    created_at: str | None = None
    position: int | None = None
    transaction_id: int | None = None
