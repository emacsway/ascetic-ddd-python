"""
MongoDB-like query operators for faker providers.

This module provides a query DSL for specifying criteria:
- $eq: equality check
- $ne, $gt, $gte, $lt, $lte: comparison operators
- $in: value in list
- $is_null: null check
- $not: logical negation
- $any: existential quantifier (at least one array element matches)
- $all: universal quantifier (every array element matches)
- $len: array length predicate
- $rel: constraints for related aggregate (ReferenceProvider)
- $or: logical OR of expressions

Examples:
    # Scalar value
    {'$eq': 27}

    # Composite PK
    {'tenant_id': {'$eq': 15}, 'local_id': {'$eq': 27}}

    # Null check
    {'deleted_at': {'$is_null': True}}

    # Negation
    {'status': {'$not': {'$eq': 'deleted'}}}

    # Any array element matches
    {'items': {'$any': {'status': {'$eq': 'shipped'}}}}

    # All array elements match
    {'items': {'$all': {'status': {'$eq': 'active'}}}}

    # Array length predicate
    {'items': {'$len': {'$gt': 2}}}

    # Related aggregate criteria
    {'$rel': {'is_active': {'$eq': True}, 'status': {'$eq': 'active'}}}

    # Combined: criteria + PK for ReferenceProvider
    {'$rel': {'is_active': {'$eq': True}, 'id': {'$eq': 27}}}
"""

from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator,
    IQueryVisitor,
    EqOperator,
    IsNullOperator,
    NotOperator,
    AnyElementOperator,
    AllElementsOperator,
    LenOperator,
    RelOperator,
    CompositeQuery,
)
from ascetic_ddd.faker.domain.query.operators import MergeConflict
from ascetic_ddd.faker.domain.query.parser import QueryParser, parse_query
from ascetic_ddd.faker.domain.query.visitors import (
    QueryToDictVisitor,
    QueryToPlainValueVisitor,
    query_to_dict,
    query_to_plain_value,
)
from ascetic_ddd.faker.domain.query.evaluate_visitor import (
    IObjectResolver,
    EvaluateWalker,
    EvaluateVisitor,
)

__all__ = (
    'IQueryOperator',
    'IQueryVisitor',
    'EqOperator',
    'IsNullOperator',
    'NotOperator',
    'AnyElementOperator',
    'AllElementsOperator',
    'LenOperator',
    'RelOperator',
    'CompositeQuery',
    'MergeConflict',
    'QueryParser',
    'parse_query',
    'QueryToDictVisitor',
    'QueryToPlainValueVisitor',
    'query_to_dict',
    'query_to_plain_value',
    'IObjectResolver',
    'EvaluateWalker',
    'EvaluateVisitor',
)
