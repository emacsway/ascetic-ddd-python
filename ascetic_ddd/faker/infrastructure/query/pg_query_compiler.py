"""
PostgreSQL query compiler for MongoDB-like query operators.

Compiles IQueryOperator tree into PostgreSQL SQL with JSONB containment (@>).

Features:
- $eq operators are collapsed into single JSON for efficient GIN index usage
- $rel operators generate EXISTS subqueries for related aggregates
- Extensible via Visitor pattern for future operators
"""
import dataclasses
import functools
import json
import typing
from collections.abc import Callable

from psycopg.types.json import Jsonb

from ascetic_ddd.faker.domain.query.operators import (
    IQueryVisitor, IQueryOperator, EqOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.infrastructure.utils.json import JSONEncoder

__all__ = ('PgQueryCompiler',)

T = typing.TypeVar('T')


class PgQueryCompiler(IQueryVisitor[None]):
    """
    Compiles query operators into PostgreSQL SQL.

    Uses JSONB containment operator (@>) for efficient indexing.
    $eq values are collapsed into single JSON for one index lookup.

    Example:
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(query)
        # sql: "value @> %s"
        # params: (Jsonb({'status': 'active', 'type': 'premium'}),)
    """

    _target_value_expr: str
    _aggregate_provider_accessor: Callable[[], typing.Any] | None
    _sql_parts: list[str]
    _params: list[typing.Any]

    __slots__ = ('_target_value_expr', '_aggregate_provider_accessor', '_sql_parts', '_params')

    def __init__(
        self,
        target_value_expr: str = "value",
        aggregate_provider_accessor: Callable[[], typing.Any] | None = None
    ):
        """
        Args:
            target_value_expr: SQL expression for the JSONB column (e.g., "value", "rt.value")
            aggregate_provider_accessor: Accessor for AggregateProvider (for $rel subqueries)
        """
        self._target_value_expr = target_value_expr
        self._aggregate_provider_accessor = aggregate_provider_accessor
        self._sql_parts = []
        self._params = []

    @property
    def sql(self) -> str:
        """Returns compiled SQL condition."""
        if not self._sql_parts:
            return ""
        return " AND ".join(self._sql_parts)

    @property
    def params(self) -> tuple[typing.Any, ...]:
        """Returns SQL parameters."""
        return tuple(self._params)

    def compile(self, query: IQueryOperator) -> tuple[str, tuple[typing.Any, ...]]:
        """
        Compile query into SQL.

        Args:
            query: Query operator tree

        Returns:
            Tuple of (sql, params)
        """
        self._sql_parts = []
        self._params = []
        query.accept(self)
        return self.sql, self.params

    def visit_eq(self, op: EqOperator) -> None:
        """
        Compile $eq operator.

        $eq compiles to JSONB containment: value @> '{"field": value}'
        """
        self._sql_parts.append(f"{self._target_value_expr} @> %s")
        self._params.append(self._encode(op.value))

    def visit_rel(self, op: RelOperator) -> None:
        """
        Compile $rel operator.

        If aggregate_provider_accessor is available:
        - FK fields generate EXISTS subqueries
        - Non-FK fields use simple @>

        Without accessor: all constraints collapsed into one @>.
        """
        if self._aggregate_provider_accessor is None:
            # No accessor - collect all $eq values into one JSON
            eq_values = self._collect_eq_values(op)
            if eq_values:
                self._sql_parts.append(f"{self._target_value_expr} @> %s")
                self._params.append(self._encode(eq_values))
            return

        self._compile_rel_with_provider(op)

    def visit_composite(self, op: CompositeQuery) -> None:
        """
        Compile CompositeQuery.

        All $eq values are collapsed into single JSON for one @> check.
        Non-$eq operators are compiled separately.
        """
        eq_values: dict[str, typing.Any] = {}
        non_eq_ops: list[tuple[str, IQueryOperator]] = []

        for field, field_op in op.fields.items():
            if isinstance(field_op, EqOperator):
                eq_values[field] = field_op.value
            else:
                non_eq_ops.append((field, field_op))

        # All $eq in one @>
        if eq_values:
            self._sql_parts.append(f"{self._target_value_expr} @> %s")
            self._params.append(self._encode(eq_values))

        # Non-$eq operators separately
        for field, field_op in non_eq_ops:
            field_op.accept(self)

    def _compile_rel_with_provider(self, op: RelOperator) -> None:
        """Compile $rel using aggregate_provider for subqueries."""
        from ascetic_ddd.faker.domain.providers.interfaces import IReferenceProvider

        agg_provider = self._aggregate_provider_accessor()
        providers = agg_provider.providers

        # Separate simple and FK constraints
        simple_values: dict[str, typing.Any] = {}

        for field, field_op in op.query.fields.items():
            provider = providers.get(field)

            if isinstance(provider, IReferenceProvider):
                # FK - build EXISTS subquery
                self._build_rel_subquery(field, field_op, provider)
            else:
                # Non-FK - collect for simple @>
                eq_value = self._collect_eq_values(field_op)
                if eq_value is not None:
                    simple_values[field] = eq_value

        # Simple values in one @>
        if simple_values:
            self._sql_parts.append(f"{self._target_value_expr} @> %s")
            self._params.append(self._encode(simple_values))

    def _build_rel_subquery(
        self,
        field: str,
        field_op: IQueryOperator,
        ref_provider: typing.Any
    ) -> None:
        """Build EXISTS subquery for FK field."""
        related_provider = ref_provider.aggregate_provider

        if not hasattr(related_provider, '_repository'):
            # No repository - fallback to simple @>
            eq_value = self._collect_eq_values(field_op)
            if eq_value is not None:
                self._sql_parts.append(f"{self._target_value_expr} @> %s")
                self._params.append(self._encode({field: eq_value}))
            return

        related_table = related_provider._repository.table

        # Recursively compile nested query
        nested_compiler = PgQueryCompiler(
            target_value_expr="rt.value",
            aggregate_provider_accessor=lambda rp=related_provider: rp
        )

        # Convert field_op to pattern for nested compilation
        if isinstance(field_op, RelOperator):
            # Already $rel - compile its constraints
            for nested_field, nested_op in field_op.query.fields.items():
                nested_compiler._compile_field(nested_field, nested_op)
        else:
            # Not $rel - treat as id constraint
            field_op.accept(nested_compiler)

        if nested_compiler.sql:
            sql = (
                f"EXISTS (SELECT 1 FROM {related_table} rt "
                f"WHERE {nested_compiler.sql} AND rt.value_id = {self._target_value_expr}->'{field}')"
            )
            self._sql_parts.append(sql)
            self._params.extend(nested_compiler.params)

    def _compile_field(self, field: str, op: IQueryOperator) -> None:
        """Compile single field constraint."""
        if isinstance(op, EqOperator):
            self._sql_parts.append(f"{self._target_value_expr} @> %s")
            self._params.append(self._encode({field: op.value}))
        else:
            op.accept(self)

    def _collect_eq_values(self, op: IQueryOperator) -> typing.Any:
        """
        Collect all $eq values from operator tree into dict.

        Returns None if no $eq values found.
        """
        if isinstance(op, EqOperator):
            return op.value
        elif isinstance(op, RelOperator):
            return self._collect_eq_values(op.query)
        elif isinstance(op, CompositeQuery):
            result = {}
            for field, field_op in op.fields.items():
                val = self._collect_eq_values(field_op)
                if val is not None:
                    result[field] = val
            return result if result else None
        return None

    @staticmethod
    def _encode(obj: typing.Any) -> Jsonb:
        """Encode object as JSONB for psycopg."""
        if dataclasses.is_dataclass(obj):
            obj = dataclasses.asdict(obj)
        dumps = functools.partial(json.dumps, cls=JSONEncoder)
        return Jsonb(obj, dumps)
