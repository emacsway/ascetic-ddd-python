"""Transactional Outbox pattern for reliable message publishing.

See init.sql for schema and detailed documentation.
"""

from ascetic_ddd.outbox.interfaces import IOutbox, IOutboxPublisher
from ascetic_ddd.outbox.message import OutboxMessage
from ascetic_ddd.outbox.pg_outbox import PgOutbox


__all__ = (
    'IOutbox',
    'IOutboxPublisher',
    'OutboxMessage',
    'PgOutbox',
)
