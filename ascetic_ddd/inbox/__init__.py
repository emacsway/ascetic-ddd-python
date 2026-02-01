"""Inbox pattern for idempotent message processing with causal consistency.

See README.md for detailed documentation.
"""

from ascetic_ddd.inbox.inbox import Inbox
from ascetic_ddd.inbox.interfaces import IInbox
from ascetic_ddd.inbox.message import InboxMessage
from ascetic_ddd.inbox.partition_strategy import (
    IPartitionKeyStrategy,
    StreamPartitionKeyStrategy,
    UriPartitionKeyStrategy,
)


__all__ = (
    'IInbox',
    'IPartitionKeyStrategy',
    'Inbox',
    'InboxMessage',
    'StreamPartitionKeyStrategy',
    'UriPartitionKeyStrategy',
)
