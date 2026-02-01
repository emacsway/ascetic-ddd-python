"""Partition key strategies for Inbox message distribution."""

from abc import ABCMeta, abstractmethod


__all__ = (
    'IPartitionKeyStrategy',
    'StreamPartitionKeyStrategy',
    'UriPartitionKeyStrategy',
)


class IPartitionKeyStrategy(metaclass=ABCMeta):
    """Strategy for computing partition key SQL expression."""

    @abstractmethod
    def get_sql_expression(self) -> str:
        """Return SQL expression for partition key.

        The expression is used with hashtext() for worker distribution:
        WHERE hashtext(<expression>) % num_workers = worker_id

        Returns:
            SQL expression string.
        """
        raise NotImplementedError


class StreamPartitionKeyStrategy(IPartitionKeyStrategy):
    """Partition by stream identity.

    Use this strategy when messages have causal dependencies within a stream.
    All messages for the same (tenant_id, stream_type, stream_id) go to the
    same worker, preserving causal order.

    SQL expression: tenant_id || ':' || stream_type || ':' || stream_id::text
    """

    def get_sql_expression(self) -> str:
        return "tenant_id || ':' || stream_type || ':' || stream_id::text"


class UriPartitionKeyStrategy(IPartitionKeyStrategy):
    """Partition by URI.

    Use this strategy when ordering is based on topic/partition from the broker.
    All messages with the same URI go to the same worker.

    The URI may contain a partition key suffix (e.g., "kafka://orders/order-123")
    similar to Outbox pattern.

    SQL expression: uri
    """

    def get_sql_expression(self) -> str:
        return "uri"
