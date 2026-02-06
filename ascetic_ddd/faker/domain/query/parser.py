"""
Query parser for MongoDB-like query syntax.

Two-stage processing:
1. Parsing: dict -> operator tree (full depth, no raw dicts remain)
2. Normalization: unwrap redundant EqOperator wrappers

Examples:
    parse_query({'$eq': 5})                    -> EqOperator(5)
    parse_query(5)                             -> EqOperator(5)  # implicit $eq
    parse_query({'$rel': {'status': {'$eq': 'active'}}})
                                               -> RelOperator({'status': EqOperator('active')})
    parse_query({'tenant_id': {'$eq': 15}})    -> CompositeQuery({'tenant_id': EqOperator(15)})
"""
import typing

from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator,
    EqOperator,
    RelOperator,
    CompositeQuery,
)

__all__ = ('QueryParser', 'normalize_query', 'parse_query')


class QueryParser:
    """
    Parses dict query into IQueryOperator tree.

    Minimizes reflection - simple switch on keys.
    Easy to port to Golang.
    """

    OPERATOR_PREFIX = '$'

    def parse(self, query: typing.Any) -> IQueryOperator:
        """
        Parse query into operator tree.

        Args:
            query: Query in dict format or scalar value

        Returns:
            IQueryOperator tree

        Raises:
            ValueError: If query format is invalid

        Examples:
            >>> parser = QueryParser()
            >>> parser.parse({'$eq': 5})
            EqOperator(5)
            >>> parser.parse(5)
            EqOperator(5)
            >>> parser.parse({'$rel': {'is_active': {'$eq': True}}})
            RelOperator({'is_active': EqOperator(True)})
        """
        if not isinstance(query, dict):
            # Scalar value - implicit $eq
            return EqOperator(query)

        if not query:
            raise ValueError("Empty query dict")

        # Separate operators from fields
        operators = {k: v for k, v in query.items() if k.startswith(self.OPERATOR_PREFIX)}
        fields = {k: v for k, v in query.items() if not k.startswith(self.OPERATOR_PREFIX)}

        if operators and fields:
            raise ValueError(
                f"Cannot mix operators and fields at same level. "
                f"Operators: {list(operators.keys())}, Fields: {list(fields.keys())}"
            )

        if operators:
            return self._parse_operators(operators)
        else:
            return self._parse_fields(fields)

    def _parse_operators(self, operators: dict[str, typing.Any]) -> IQueryOperator:
        """Parse operator dict (e.g., {'$eq': 5} or {'$rel': {...}})."""
        if len(operators) != 1:
            raise ValueError(
                f"Only one operator per level supported, got: {list(operators.keys())}"
            )

        op_name, op_value = next(iter(operators.items()))

        if op_name == '$eq':
            return self._parse_eq(op_value)
        elif op_name == '$rel':
            return self._parse_rel(op_value)
        else:
            raise ValueError(f"Unknown operator: {op_name}")

    def _parse_eq(self, value: typing.Any) -> EqOperator:
        """
        Parse $eq operator value to full depth.

        Dict values are recursively parsed into operator tree but $eq wrapper is preserved:
        {'$eq': {'a': 1, 'b': 2}} -> EqOperator(CompositeQuery({'a': EqOperator(1), 'b': EqOperator(2)}))

        Use normalize_query() to unwrap redundant $eq afterwards.
        """
        if isinstance(value, dict):
            return EqOperator(self.parse(value))
        return EqOperator(value)

    def _parse_rel(self, constraints: typing.Any) -> RelOperator:
        """Parse $rel operator value into RelOperator."""
        if not isinstance(constraints, dict):
            raise ValueError(f"$rel value must be dict, got: {type(constraints).__name__}")

        parsed: dict[str, IQueryOperator] = {}
        for field, value in constraints.items():
            parsed[field] = self.parse(value)
        return RelOperator(parsed)

    def _parse_fields(self, fields: dict[str, typing.Any]) -> CompositeQuery:
        """Parse field dict into CompositeQuery."""
        parsed: dict[str, IQueryOperator] = {}
        for field, value in fields.items():
            parsed[field] = self.parse(value)
        return CompositeQuery(parsed)


def normalize_query(op: IQueryOperator) -> IQueryOperator:
    """
    Normalize query by unwrapping redundant EqOperator wrappers.

    EqOperator(CompositeQuery({'a': EqOperator(1)})) -> CompositeQuery({'a': EqOperator(1)})

    Assumes tree is fully parsed (no raw dicts inside EqOperator).
    """
    if isinstance(op, EqOperator):
        if isinstance(op.value, IQueryOperator):
            # Unwrap: EqOperator(CompositeQuery(...)) -> CompositeQuery(...)
            return normalize_query(op.value)
        return op

    if isinstance(op, RelOperator):
        normalized = {k: normalize_query(v) for k, v in op.constraints.items()}
        return RelOperator(normalized)

    if isinstance(op, CompositeQuery):
        normalized = {k: normalize_query(v) for k, v in op.fields.items()}
        return CompositeQuery(normalized)

    return op


def parse_query(query: typing.Any) -> IQueryOperator:
    """
    Parse and normalize query.

    Two-stage processing:
    1. Parse dict into operator tree (full depth)
    2. Normalize: unwrap redundant EqOperator wrappers
    """
    return normalize_query(QueryParser().parse(query))
