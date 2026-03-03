"""
PostgreSQL query compiler for MongoDB-like query operators.

Compiles IQueryOperator tree into PostgreSQL SQL with JSONB containment (@>).

- EqOperator values are collected into single @> for GIN index usage
- Other operators ($gt, $gte, $lt, $lte, $ne, $in) extract JSON attribute and apply operator
- RelOperator generates EXISTS subqueries (separate table)

Field context (_field_path) is maintained for nested operators.
"""
import dataclasses
import functools
import json
import typing
from abc import ABCMeta, abstractmethod

from psycopg.types.json import Jsonb

from ascetic_ddd.faker.domain.query.operators import (
    IQueryVisitor, IQueryOperator, EqOperator, ComparisonOperator, InOperator,
    IsNullOperator, NotOperator, AnyElementOperator, AllElementsOperator,
    LenOperator, AndOperator, OrOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.infrastructure.utils.json import JSONEncoder


__all__ = ('PgQueryCompiler', 'RelationInfo', 'IRelationResolver',)


class RelationInfo(typing.NamedTuple):
    """Result of resolving a relation field."""
    table: str
    pk_field: str
    nested_resolver: 'IRelationResolver | None'


class IRelationResolver(metaclass=ABCMeta):
    """Resolves a field name to relation metadata for SQL compilation."""

    @abstractmethod
    def resolve(self, field: str) -> RelationInfo | None:
        """
        Resolve field to relation info.

        Returns RelationInfo if field is a reference (FK) to another aggregate,
        None if field is a regular (non-reference) field.
        """
        raise NotImplementedError


class PgQueryCompiler(IQueryVisitor[None]):
    """
    Compiles IQueryOperator tree into PostgreSQL SQL.

    EqOperator values within CompositeQuery are collapsed into single @>.
    RelOperator generates EXISTS subqueries for related aggregates.
    Field context (_field_path) allows future operators to build JSON extraction paths.
    """

    __slots__ = (
        '_target_value_expr', '_relation_resolver', '_alias_seq',
        '_field_path', '_eq_values', '_sql_parts', '_params'
    )

    def __init__(
        self,
        target_value_expr: str = "value",
        relation_resolver: IRelationResolver | None = None,
        _alias_seq: list[int] | None = None,
    ):
        self._target_value_expr = target_value_expr
        self._relation_resolver = relation_resolver
        self._alias_seq = _alias_seq if _alias_seq is not None else [0]
        self._field_path: list[str] = []
        self._eq_values: dict[str, typing.Any] = {}
        self._sql_parts: list[str] = []
        self._params: list[typing.Any] = []

    def _next_alias(self) -> str:
        self._alias_seq[0] += 1
        return f"rt{self._alias_seq[0]}"

    @property
    def sql(self) -> str:
        return " AND ".join(self._sql_parts) if self._sql_parts else ""

    @property
    def params(self) -> tuple[typing.Any, ...]:
        return tuple(self._params)

    def compile(self, query: IQueryOperator) -> tuple[str, tuple[typing.Any, ...]]:
        self._field_path = []
        self._eq_values = {}
        self._sql_parts = []
        self._params = []
        query.accept(self)
        self._flush_eq()
        return self.sql, self.params

    # --- Visitor methods ---

    def visit_eq(self, op: EqOperator) -> None:
        if self._field_path:
            self._collect_eq(op.value)
        else:
            self._sql_parts.append(f"{self._target_value_expr} @> %s")
            self._params.append(self._encode(op.value))

    _SQL_OPS: typing.ClassVar[dict[str, str]] = {
        '$gt': '>',
        '$gte': '>=',
        '$lt': '<',
        '$lte': '<=',
    }

    def visit_comparison(self, op: ComparisonOperator) -> None:
        if op.op == '$ne':
            self._compile_ne(op.value)
        else:
            sql_op = self._SQL_OPS[op.op]
            json_path = self._json_path_expr()
            self._sql_parts.append(f"{json_path} {sql_op} %s")
            self._params.append(op.value)

    def _compile_ne(self, value: typing.Any) -> None:
        """Compile $ne using negated JSONB containment."""
        if self._field_path:
            nested: dict[str, typing.Any] = {}
            target = nested
            for key in self._field_path[:-1]:
                target[key] = {}
                target = target[key]
            target[self._field_path[-1]] = value
            self._sql_parts.append(f"NOT ({self._target_value_expr} @> %s)")
            self._params.append(self._encode(nested))
        else:
            self._sql_parts.append(f"NOT ({self._target_value_expr} @> %s)")
            self._params.append(self._encode(value))

    def visit_in(self, op: InOperator) -> None:
        or_parts: list[str] = []
        for value in op.values:
            if self._field_path:
                nested: dict[str, typing.Any] = {}
                target = nested
                for key in self._field_path[:-1]:
                    target[key] = {}
                    target = target[key]
                target[self._field_path[-1]] = value
                or_parts.append(f"{self._target_value_expr} @> %s")
                self._params.append(self._encode(nested))
            else:
                or_parts.append(f"{self._target_value_expr} @> %s")
                self._params.append(self._encode(value))
        if len(or_parts) == 1:
            self._sql_parts.append(or_parts[0])
        else:
            self._sql_parts.append(f"({' OR '.join(or_parts)})")

    def visit_is_null(self, op: IsNullOperator) -> None:
        json_path = self._json_path_expr() if self._field_path else self._target_value_expr
        if op.value:
            self._sql_parts.append("%s IS NULL" % json_path)
        else:
            self._sql_parts.append("%s IS NOT NULL" % json_path)

    def visit_and(self, op: AndOperator) -> None:
        for operand in op.operands:
            operand.accept(self)

    def visit_or(self, op: OrOperator) -> None:
        or_parts: list[str] = []
        for operand in op.operands:
            sub_compiler = PgQueryCompiler(
                target_value_expr=self._target_value_expr,
                relation_resolver=self._relation_resolver,
                _alias_seq=self._alias_seq,
            )
            sub_compiler._field_path = list(self._field_path)
            operand.accept(sub_compiler)
            sub_compiler._flush_eq()
            if sub_compiler.sql:
                or_parts.append(sub_compiler.sql)
                self._params.extend(sub_compiler.params)
        if or_parts:
            self._sql_parts.append(f"({' OR '.join(or_parts)})")

    def visit_not(self, op: NotOperator) -> None:
        sub_compiler = PgQueryCompiler(
            target_value_expr=self._target_value_expr,
            relation_resolver=self._relation_resolver,
            _alias_seq=self._alias_seq,
        )
        sub_compiler._field_path = list(self._field_path)
        op.operand.accept(sub_compiler)
        sub_compiler._flush_eq()
        if sub_compiler.sql:
            self._sql_parts.append("NOT (%s)" % sub_compiler.sql)
            self._params.extend(sub_compiler.params)

    def visit_any_element(self, op: AnyElementOperator) -> None:
        json_path = self._json_path_expr() if self._field_path else self._target_value_expr
        alias = self._next_alias()
        sub_compiler = PgQueryCompiler(
            target_value_expr=alias,
            relation_resolver=self._relation_resolver,
            _alias_seq=self._alias_seq,
        )
        op.query.accept(sub_compiler)
        sub_compiler._flush_eq()
        if sub_compiler.sql:
            sql = (
                "EXISTS (SELECT 1 FROM jsonb_array_elements(%s) AS %s "
                "WHERE %s)"
                % (json_path, alias, sub_compiler.sql)
            )
            self._sql_parts.append(sql)
            self._params.extend(sub_compiler.params)

    def visit_all_elements(self, op: AllElementsOperator) -> None:
        json_path = self._json_path_expr() if self._field_path else self._target_value_expr
        alias = self._next_alias()
        sub_compiler = PgQueryCompiler(
            target_value_expr=alias,
            relation_resolver=self._relation_resolver,
            _alias_seq=self._alias_seq,
        )
        op.query.accept(sub_compiler)
        sub_compiler._flush_eq()
        if sub_compiler.sql:
            sql = (
                "NOT EXISTS (SELECT 1 FROM jsonb_array_elements(%s) AS %s "
                "WHERE NOT (%s))"
                % (json_path, alias, sub_compiler.sql)
            )
            self._sql_parts.append(sql)
            self._params.extend(sub_compiler.params)

    def visit_len(self, op: LenOperator) -> None:
        json_path = self._json_path_expr() if self._field_path else self._target_value_expr
        len_expr = "jsonb_array_length(%s)" % json_path
        self._compile_scalar_predicate(len_expr, op.query)

    def _compile_scalar_predicate(self, expr: str, query: IQueryOperator) -> None:
        """Compile a predicate against a scalar SQL expression (e.g. jsonb_array_length).

        Unlike visit_eq/visit_comparison which use JSONB containment (@>),
        this generates standard SQL comparisons (=, >, <, etc.) for plain values.
        """
        if isinstance(query, EqOperator):
            self._sql_parts.append("%s = %%s" % expr)
            self._params.append(query.value)
        elif isinstance(query, ComparisonOperator):
            if query.op == '$ne':
                self._sql_parts.append("%s != %%s" % expr)
                self._params.append(query.value)
            else:
                sql_op = self._SQL_OPS[query.op]
                self._sql_parts.append("%s %s %%s" % (expr, sql_op))
                self._params.append(query.value)
        elif isinstance(query, InOperator):
            or_parts = ["%s = %%s" % expr for _ in query.values]
            self._params.extend(query.values)
            if len(or_parts) == 1:
                self._sql_parts.append(or_parts[0])
            else:
                self._sql_parts.append("(%s)" % " OR ".join(or_parts))
        elif isinstance(query, IsNullOperator):
            if query.value:
                self._sql_parts.append("%s IS NULL" % expr)
            else:
                self._sql_parts.append("%s IS NOT NULL" % expr)
        elif isinstance(query, NotOperator):
            self._compile_scalar_predicate_not(expr, query)
        elif isinstance(query, AndOperator):
            for operand in query.operands:
                self._compile_scalar_predicate(expr, operand)
        elif isinstance(query, OrOperator):
            or_parts_list: list[str] = []
            saved_sql = list(self._sql_parts)
            saved_params = list(self._params)
            for operand in query.operands:
                self._sql_parts = []
                self._params = []
                self._compile_scalar_predicate(expr, operand)
                if self._sql_parts:
                    or_parts_list.append(" AND ".join(self._sql_parts))
                    saved_params.extend(self._params)
            self._sql_parts = saved_sql
            self._params = saved_params
            if or_parts_list:
                self._sql_parts.append("(%s)" % " OR ".join(or_parts_list))

    def _compile_scalar_predicate_not(self, expr: str, query: NotOperator) -> None:
        """Compile NOT for scalar predicate."""
        saved_sql = list(self._sql_parts)
        saved_params = list(self._params)
        self._sql_parts = []
        self._params = []
        self._compile_scalar_predicate(expr, query.operand)
        if self._sql_parts:
            inner = " AND ".join(self._sql_parts)
            saved_sql.append("NOT (%s)" % inner)
            saved_params.extend(self._params)
        self._sql_parts = saved_sql
        self._params = saved_params

    def visit_composite(self, op: CompositeQuery) -> None:
        for field, field_op in op.fields.items():
            if isinstance(field_op, RelOperator):
                self._compile_rel_field(field, field_op)
            else:
                self._field_path.append(field)
                field_op.accept(self)
                self._field_path.pop()

    def visit_rel(self, op: RelOperator) -> None:
        if self._relation_resolver is None:
            raise TypeError(
                "Cannot compile $rel without relation_resolver."
            )
        if self._field_path:
            field = self._field_path.pop()
            self._compile_rel_field(field, op)
        else:
            op.query.accept(self)

    # --- Eq collection ---

    def _collect_eq(self, value: typing.Any) -> None:
        target = self._eq_values
        for key in self._field_path[:-1]:
            target = target.setdefault(key, {})
        target[self._field_path[-1]] = value

    def _flush_eq(self) -> None:
        if self._eq_values:
            self._sql_parts.insert(0, f"{self._target_value_expr} @> %s")
            self._params.insert(0, self._encode(self._eq_values))

    # --- $rel compilation ---

    def _compile_rel_field(self, field: str, op: RelOperator) -> None:
        if self._relation_resolver is None:
            raise TypeError(
                "Cannot compile $rel without relation_resolver."
            )

        relation_info = self._relation_resolver.resolve(field)

        if relation_info is not None:
            self._build_exists_subquery(field, op, relation_info)
        else:
            nested = self._to_dict(op.query)
            if nested is not None:
                self._sql_parts.append(f"{self._target_value_expr} @> %s")
                self._params.append(self._encode({field: nested}))

    def _build_exists_subquery(
        self,
        field: str,
        op: RelOperator,
        relation_info: typing.Any,
    ) -> None:
        alias = self._next_alias()

        nested_compiler = PgQueryCompiler(
            target_value_expr=f"{alias}.value",
            relation_resolver=relation_info.nested_resolver,
            _alias_seq=self._alias_seq,
        )
        op.query.accept(nested_compiler)
        nested_compiler._flush_eq()

        if nested_compiler.sql:
            sql = (
                f"EXISTS (SELECT 1 FROM {relation_info.table} {alias} "
                f"WHERE {nested_compiler.sql} AND "
                f"{alias}.{relation_info.pk_field} = {self._target_value_expr}->'{field}')"
            )
            self._sql_parts.append(sql)
            self._params.extend(nested_compiler.params)

    # --- Helpers ---

    def _json_path_expr(self) -> str:
        """Build JSON extraction expression from _field_path.

        ['status'] -> value->'status'
        ['address', 'city'] -> value->'address'->'city'
        """
        expr = self._target_value_expr
        for key in self._field_path:
            expr += f"->'{key}'"
        return expr

    @staticmethod
    def _to_dict(op: IQueryOperator) -> typing.Any:
        if isinstance(op, EqOperator):
            return op.value
        elif isinstance(op, CompositeQuery):
            result = {}
            for field, field_op in op.fields.items():
                val = PgQueryCompiler._to_dict(field_op)
                if val is not None:
                    result[field] = val
            return result if result else None
        return None

    @staticmethod
    def _encode(obj: typing.Any) -> Jsonb:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            obj = dataclasses.asdict(obj)
        dumps = functools.partial(json.dumps, cls=JSONEncoder)
        return Jsonb(obj, dumps)
