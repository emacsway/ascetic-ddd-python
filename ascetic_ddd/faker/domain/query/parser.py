"""
Query parser for MongoDB-like query syntax.

Parses dict queries into operator tree.

Examples:
    parse({'$eq': 5})                    -> EqOperator(5)
    parse(5)                             -> EqOperator(5)  # implicit $eq
    parse({'$rel': {'status': {'$eq': 'active'}}})
                                         -> RelOperator({'status': EqOperator('active')})
    parse({'tenant_id': {'$eq': 15}})    -> CompositeQuery({'tenant_id': EqOperator(15)})
"""
import typing

from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator,
    EqOperator,
    RelOperator,
    CompositeQuery,
)

__all__ = ('QueryParser',)


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

    def _parse_eq(self, value: typing.Any) -> IQueryOperator:
        """
        Parse $eq operator value.

        Normalizes dict values by pushing $eq down:
        {'$eq': {'a': 1, 'b': 2}} -> CompositeQuery({'a': EqOperator(1), 'b': EqOperator(2)})
        """
        if isinstance(value, dict):
            # Push $eq down: {'$eq': {'a': 1}} -> {'a': {'$eq': 1}}
            return self._parse_fields(value)
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
