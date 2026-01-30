"""Inbox message - structure for incoming integration messages."""

from dataclasses import dataclass, field
from typing import Any


__all__ = (
    'InboxMessage',
)


@dataclass
class InboxMessage:
    """Incoming integration message for the Inbox pattern.

    Attributes:
        tenant_id: Tenant identifier.
        stream_type: Type of the event stream (e.g., aggregate type).
        stream_id: Identifier of the stream (e.g., aggregate ID).
        stream_position: Position in the stream (monotonically increasing).
        event_type: Type of the event.
        event_version: Version of the event schema.
        payload: Event payload data.
        metadata: Optional event metadata (may contain event_id, causal_dependencies, etc.).
        received_position: Position when message was received (auto-assigned by DB).
        processed_position: Position when message was processed (None if not processed).
    """
    tenant_id: str
    stream_type: str
    stream_id: dict[str, Any]
    stream_position: int
    event_type: str
    event_version: int
    payload: dict[str, Any]
    metadata: dict[str, Any] | None = None
    received_position: int | None = None
    processed_position: int | None = None

    @property
    def causal_dependencies(self) -> list[dict[str, Any]]:
        """Get causal dependencies from metadata.

        Returns:
            List of dependency descriptors, each containing:
            - tenant_id, stream_type, stream_id, stream_position
        """
        if self.metadata is None:
            return []
        return self.metadata.get('causal_dependencies', [])

    @property
    def event_id(self) -> str | None:
        """Get event_id from metadata if present."""
        if self.metadata is None:
            return None
        return self.metadata.get('event_id')
