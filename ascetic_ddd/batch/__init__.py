"""Batch query processing module."""
from ascetic_ddd.batch.interfaces import (
    IQueryEvaluator,
    IMultiQuerier,
    IDeferredCursor,
    IDeferredConnection,
    IDeferredPgSession,
)
from ascetic_ddd.batch.utils import (
    is_insert_query,
    is_autoincrement_insert_query,
)
from ascetic_ddd.batch.multi_query import (
    MultiQueryBase,
    MultiQuery,
    AutoincrementMultiInsertQuery,
)
from ascetic_ddd.batch.query_collector import QueryCollector, ConnectionCollector, CursorCollector


__all__ = (
    # Interfaces
    "IQueryEvaluator",
    "IMultiQuerier",
    "IDeferredCursor",
    "IDeferredConnection",
    "IDeferredPgSession",
    # Utils
    "is_insert_query",
    "is_autoincrement_insert_query",
    # Multi-query
    "MultiQueryBase",
    "MultiQuery",
    "AutoincrementMultiInsertQuery",
    # Query collector
    "QueryCollector",
    "ConnectionCollector",
    "CursorCollector",
)
