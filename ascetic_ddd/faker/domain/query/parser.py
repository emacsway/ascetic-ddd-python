"""
Query parser for MongoDB-like query syntax.

Two-stage processing:
1. Parsing: dict -> operator tree (full depth, no raw dicts remain)
2. Normalization: unwrap redundant EqOperator wrappers

Examples:
    parse_query({'$eq': 5})                    -> EqOperator(5)
    parse_query(5)                             -> EqOperator(5)  # implicit $eq
    parse_query({'$rel': {'status': {'$eq': 'active'}}})
                                               -> RelOperator(CompositeQuery({'status': EqOperator('active')}))
    parse_query({'tenant_id': {'$eq': 15}})    -> CompositeQuery({'tenant_id': EqOperator(15)})
"""
import typing

from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator,
    EqOperator,
    ComparisonOperator,
    InOperator,
    IsNullOperator,
    NotOperator,
    AnyElementOperator,
    AllElementsOperator,
    LenOperator,
    AndOperator,
    OrOperator,
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
            RelOperator(CompositeQuery({'is_active': EqOperator(True)}))
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
        """Parse operator dict (e.g., {'$eq': 5} or {'$gt': 5, '$lt': 10})."""
        if len(operators) == 1:
            return self._parse_single_operator(*next(iter(operators.items())))

        # Multiple operators at same level → implicit AND
        parsed = []
        for op_name, op_value in operators.items():
            parsed.append(self._parse_single_operator(op_name, op_value))
        return AndOperator(tuple(parsed))

    def _parse_single_operator(self, op_name: str, op_value: typing.Any) -> IQueryOperator:
        """Parse a single operator by name."""
        if op_name == '$eq':
            return self._parse_eq(op_value)
        elif op_name in ComparisonOperator.SUPPORTED_OPS:
            return ComparisonOperator(op_name, op_value)
        elif op_name == '$in':
            return self._parse_in(op_value)
        elif op_name == '$or':
            return self._parse_or(op_value)
        elif op_name == '$is_null':
            return self._parse_is_null(op_value)
        elif op_name == '$not':
            return self._parse_not(op_value)
        elif op_name == '$any':
            return self._parse_any(op_value)
        elif op_name == '$all':
            return self._parse_all(op_value)
        elif op_name == '$len':
            return self._parse_len(op_value)
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

    def _parse_or(self, operands: typing.Any) -> OrOperator:
        """Parse $or operator value into OrOperator."""
        if not isinstance(operands, list):
            raise ValueError(f"$or value must be list, got: {type(operands).__name__}")
        if len(operands) < 2:
            raise ValueError(f"$or requires at least 2 operands, got: {len(operands)}")
        return OrOperator(tuple(self.parse(operand) for operand in operands))

    def _parse_in(self, values: typing.Any) -> InOperator:
        """Parse $in operator value into InOperator."""
        if not isinstance(values, list):
            raise ValueError(f"$in value must be list, got: {type(values).__name__}")
        if len(values) < 1:
            raise ValueError(f"$in requires at least 1 value, got: {len(values)}")
        return InOperator(tuple(values))

    def _parse_is_null(self, value: typing.Any) -> IsNullOperator:
        """Parse $is_null operator value into IsNullOperator."""
        if not isinstance(value, bool):
            raise ValueError("$is_null value must be bool, got: %s" % type(value).__name__)
        return IsNullOperator(value)

    def _parse_not(self, value: typing.Any) -> NotOperator:
        """Parse $not operator value into NotOperator."""
        return NotOperator(self.parse(value))

    def _parse_any(self, value: typing.Any) -> AnyElementOperator:
        """Parse $any operator value into AnyElementOperator."""
        if not isinstance(value, dict):
            raise ValueError("$any value must be dict, got: %s" % type(value).__name__)
        return AnyElementOperator(self.parse(value))

    def _parse_all(self, value: typing.Any) -> AllElementsOperator:
        """Parse $all operator value into AllElementsOperator."""
        if not isinstance(value, dict):
            raise ValueError("$all value must be dict, got: %s" % type(value).__name__)
        return AllElementsOperator(self.parse(value))

    def _parse_len(self, value: typing.Any) -> LenOperator:
        """Parse $len operator value into LenOperator."""
        return LenOperator(self.parse(value))

    def _parse_rel(self, constraints: typing.Any) -> RelOperator:
        """Parse $rel operator value into RelOperator."""
        if not isinstance(constraints, dict):
            raise ValueError(f"$rel value must be dict, got: {type(constraints).__name__}")

        return RelOperator(self._parse_fields(constraints))

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
        normalized = normalize_query(op.query)
        assert isinstance(normalized, CompositeQuery)
        return RelOperator(normalized)

    if isinstance(op, NotOperator):
        return NotOperator(normalize_query(op.operand))

    if isinstance(op, AnyElementOperator):
        return AnyElementOperator(normalize_query(op.query))

    if isinstance(op, AllElementsOperator):
        return AllElementsOperator(normalize_query(op.query))

    if isinstance(op, LenOperator):
        return LenOperator(normalize_query(op.query))

    if isinstance(op, AndOperator):
        return AndOperator(tuple(normalize_query(operand) for operand in op.operands))

    if isinstance(op, OrOperator):
        return OrOperator(tuple(normalize_query(operand) for operand in op.operands))

    if isinstance(op, CompositeQuery):
        normalized_fields: dict[str, IQueryOperator] = {k: normalize_query(v) for k, v in op.fields.items()}
        return CompositeQuery(normalized_fields)

    return op


def parse_query(query: typing.Any) -> IQueryOperator:
    """
    Parse and normalize query.

    Two-stage processing:
    1. Parse dict into operator tree (full depth)
    2. Normalize: unwrap redundant EqOperator wrappers
    """
    return normalize_query(QueryParser().parse(query))
