"""Interfaces for the Inbox pattern."""

from abc import ABCMeta, abstractmethod
from typing import AsyncIterator, TypeAlias, Callable, Awaitable
from ascetic_ddd.inbox.message import InboxMessage
from ascetic_ddd.seedwork.infrastructure.session.interfaces import IPgSession


__all__ = (
    'IInbox',
    'ISubscriber',
)

ISubscriber: TypeAlias = Callable[[IPgSession, InboxMessage], Awaitable]


class IInbox(metaclass=ABCMeta):
    """Interface for the Inbox pattern.

    The Inbox pattern ensures:
    - Idempotency of incoming integration messages
    - Causal consistency by checking causal dependencies
    - Reliable message processing with at-least-once delivery
    """

    @abstractmethod
    async def publish(self, message: 'InboxMessage') -> None:
        """Receive and store an incoming message.

        The message is stored in the inbox table. If a message with the same
        primary key (tenant_id, stream_type, stream_id, stream_position) already
        exists, it is ignored (idempotency).

        Args:
            message: The incoming integration message.
        """
        raise NotImplementedError

    @abstractmethod
    async def dispatch(
            self,
            subscriber: ISubscriber,
            worker_id: int = 0,
            num_workers: int = 1,
    ) -> bool:
        """Process the next unprocessed message.

        Selects the first message with processed_position IS NULL,
        ordered by received_position ASC, filtered by partition.

        Before processing, checks that all causal dependencies are satisfied
        (exist in the inbox and have processed_position IS NOT NULL).

        If dependencies are not satisfied, skips to the next message.

        Args:
            subscriber: Callback to process the message.
            worker_id: This worker's ID (0 to num_workers-1).
            num_workers: Total number of workers for partitioning.

        Returns:
            True if a message was processed, False if no processable messages.
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

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[tuple['IPgSession', 'InboxMessage']]:
        """Return async iterator for continuous message processing.

        Usage:
            async for session, message in inbox:
                await handle_message(session, message)

        Yields:
            Tuple of (session, message) for each processable message.
        """
        raise NotImplementedError

    @abstractmethod
    async def run(
            self,
            subscriber: ISubscriber,
            process_id: int = 0,
            num_processes: int = 1,
            concurrency: int = 1,
            poll_interval: float = 1.0,
    ) -> None:
        """Run message processing with partitioned workers.

        Each coroutine processes its own partitions:
          effective_id = process_id * concurrency + local_id
          effective_total = num_processes * concurrency

        Args:
            subscriber: Callback to process each message.
            process_id: This process's ID (0 to num_processes-1).
            num_processes: Total number of processes.
            concurrency: Number of coroutines within this process.
            poll_interval: Seconds to wait when no messages available.
        """
        raise NotImplementedError
