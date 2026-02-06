"""
MongoDB-like query operators for faker providers.

This module provides a query DSL for specifying criteria:
- $eq: equality check
- $rel: constraints for related aggregate (ReferenceProvider)

Examples:
    # Scalar value
    {'$eq': 27}

    # Composite PK
    {'tenant_id': {'$eq': 15}, 'local_id': {'$eq': 27}}

    # Related aggregate criteria
    {'$rel': {'is_active': {'$eq': True}, 'status': {'$eq': 'active'}}}

    # Combined: criteria + PK for ReferenceProvider
    {'$rel': {'is_active': {'$eq': True}, 'id': {'$eq': 27}}}
"""

from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator,
    IQueryVisitor,
    EqOperator,
    RelOperator,
    CompositeQuery,
)
from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.faker.domain.query.merger import QueryMerger
from ascetic_ddd.faker.domain.query.visitors import (
    QueryToDictVisitor,
    QueryToPlainValueVisitor,
    query_to_dict,
    query_to_plain_value,
)

__all__ = (
    'IQueryOperator',
    'IQueryVisitor',
    'EqOperator',
    'RelOperator',
    'CompositeQuery',
    'QueryParser',
    'QueryMerger',
    'QueryToDictVisitor',
    'QueryToPlainValueVisitor',
    'query_to_dict',
    'query_to_plain_value',
)
