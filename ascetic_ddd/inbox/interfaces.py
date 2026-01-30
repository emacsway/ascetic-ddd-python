"""Interfaces for the Inbox pattern."""

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ascetic_ddd.inbox.message import InboxMessage
    from ascetic_ddd.seedwork.infrastructure.session.interfaces import IPgSession


__all__ = (
    'IInbox',
)


class IInbox(metaclass=ABCMeta):
    """Interface for the Inbox pattern.

    The Inbox pattern ensures:
    - Idempotency of incoming integration messages
    - Causal consistency by checking causal dependencies
    - Reliable message processing with at-least-once delivery
    """

    @abstractmethod
    async def receive(self, message: 'InboxMessage') -> None:
        """Receive and store an incoming message.

        The message is stored in the inbox table. If a message with the same
        primary key (tenant_id, stream_type, stream_id, stream_position) already
        exists, it is ignored (idempotency).

        Args:
            message: The incoming integration message.
        """
        raise NotImplementedError

    @abstractmethod
    async def handle(self) -> bool:
        """Process the next unprocessed message.

        Selects the first message with processed_position IS NULL,
        ordered by received_position ASC.

        Before processing, checks that all causal dependencies are satisfied
        (exist in the inbox and have processed_position IS NOT NULL).

        If dependencies are not satisfied, skips to the next message.

        Returns:
            True if a message was processed, False if no processable messages.
        """
        raise NotImplementedError

    @abstractmethod
    async def do_handle(self, session: 'IPgSession', message: 'InboxMessage') -> None:
        """Process a single message.

        This method should be overridden in subclasses to implement
        the actual message handling logic (e.g., dispatch to mediator).

        Args:
            session: Database session for the transaction.
            message: The message to process.
        """
        raise NotImplementedError

    @abstractmethod
    async def setup(self) -> None:
        """Initialize the inbox (create tables if needed)."""
        raise NotImplementedError

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup resources."""
        raise NotImplementedError
