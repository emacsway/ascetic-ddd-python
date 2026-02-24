"""
Query visitors for transforming IQueryOperator trees.

Provides visitors for converting query operators to different formats.
Eliminates code duplication across providers and specifications.
"""
import typing

from ascetic_ddd.faker.domain.query.operators import (
    IQueryVisitor, IQueryOperator, EqOperator, ComparisonOperator, InOperator,
    IsNullOperator, AndOperator, OrOperator, RelOperator, CompositeQuery
)

__all__ = (
    'QueryToDictVisitor',
    'QueryToPlainValueVisitor',
    'query_to_plain_value',
    'query_to_dict',
    'dict_to_query',
)


class QueryToDictVisitor(IQueryVisitor[dict]):
    """
    Converts IQueryOperator to dict format with operators.

    Example:
        EqOperator(5) -> {'$eq': 5}
        RelOperator(CompositeQuery({'status': EqOperator('active')})) -> {'$rel': {'status': {'$eq': 'active'}}}
        CompositeQuery({'a': EqOperator(1)}) -> {'a': {'$eq': 1}}
    """

    def visit(self, op: IQueryOperator) -> dict:
        """Entry point for visiting."""
        return op.accept(self)

    def visit_eq(self, op: EqOperator) -> dict:
        if isinstance(op.value, IQueryOperator):
            return {'$eq': op.value.accept(self)}
        return {'$eq': op.value}

    def visit_comparison(self, op: ComparisonOperator) -> dict:
        return {op.op: op.value}

    def visit_in(self, op: InOperator) -> dict:
        return {'$in': list(op.values)}

    def visit_is_null(self, op: IsNullOperator) -> dict:
        return {'$is_null': op.value}

    def visit_and(self, op: AndOperator) -> dict:
        result: dict = {}
        for operand in op.operands:
            accepted: dict = operand.accept(self)
            result.update(accepted)
        return result

    def visit_or(self, op: OrOperator) -> dict:
        return {'$or': [operand.accept(self) for operand in op.operands]}

    def visit_rel(self, op: RelOperator) -> dict:
        return {'$rel': op.query.accept(self)}

    def visit_composite(self, op: CompositeQuery) -> dict:
        return {k: v.accept(self) for k, v in op.fields.items()}


class QueryToPlainValueVisitor(IQueryVisitor[typing.Any]):
    """
    Converts IQueryOperator to plain value (without operators).

    Extracts actual values from operators for use in specifications.

    Example:
        EqOperator(5) -> 5
        RelOperator(CompositeQuery({'status': EqOperator('active')})) -> {'status': 'active'}
        CompositeQuery({'a': EqOperator(1), 'b': EqOperator(2)}) -> {'a': 1, 'b': 2}
    """

    def visit(self, op: IQueryOperator) -> typing.Any:
        """Entry point for visiting."""
        return op.accept(self)

    def visit_eq(self, op: EqOperator) -> typing.Any:
        if isinstance(op.value, IQueryOperator):
            return op.value.accept(self)
        return op.value

    def visit_comparison(self, op: ComparisonOperator) -> typing.Any:
        return {op.op: op.value}

    def visit_in(self, op: InOperator) -> typing.Any:
        return {'$in': list(op.values)}

    def visit_is_null(self, op: IsNullOperator) -> typing.Any:
        return {'$is_null': op.value}

    def visit_and(self, op: AndOperator) -> typing.Any:
        result: dict = {}
        for operand in op.operands:
            result.update(operand.accept(self))
        return result

    def visit_or(self, op: OrOperator) -> typing.Any:
        return {'$or': [operand.accept(self) for operand in op.operands]}

    def visit_rel(self, op: RelOperator) -> dict:
        return op.query.accept(self)

    def visit_composite(self, op: CompositeQuery) -> dict:
        return {k: v.accept(self) for k, v in op.fields.items()}


# Singleton instances for convenience
_query_to_dict_visitor = QueryToDictVisitor()
_query_to_plain_value_visitor = QueryToPlainValueVisitor()


def query_to_dict(op: IQueryOperator) -> dict:
    """Convert IQueryOperator to dict format with operators."""
    return _query_to_dict_visitor.visit(op)


def query_to_plain_value(op: IQueryOperator) -> typing.Any:
    """Convert IQueryOperator to plain value without operators."""
    return _query_to_plain_value_visitor.visit(op)


def dict_to_query(value: typing.Any) -> dict:
    """
    Convert plain dict to query format with $eq operators.

    Example:
        {'a': 1, 'b': {'c': 2}} -> {'a': {'$eq': 1}, 'b': {'c': {'$eq': 2}}}
        5 -> {'$eq': 5}
    """
    if isinstance(value, dict):
        return {k: dict_to_query(v) for k, v in value.items()}
    return {'$eq': value}
