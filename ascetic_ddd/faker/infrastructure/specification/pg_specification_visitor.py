import dataclasses
import functools
import json
import typing

from psycopg.types.json import Jsonb

from ascetic_ddd.faker.infrastructure.utils.json import JSONEncoder
from ascetic_ddd.faker.domain.query.operators import IQueryOperator
from ascetic_ddd.faker.domain.query.visitors import query_to_plain_value
from ascetic_ddd.faker.domain.specification.interfaces import ISpecificationVisitor

__all__ = ("PgSpecificationVisitor",)


class PgSpecificationVisitor(ISpecificationVisitor):
    _target_value_expr: str
    _sql: str
    _params: typing.Tuple[typing.Any, ...]

    __slots__ = ("_target_value_expr", "_sql", "_params",)

    def __init__(self, target_value_expr: str = "value"):
        self._target_value_expr = target_value_expr
        self._sql = ""
        self._params = tuple()

    @property
    def sql(self) -> str:
        return self._sql

    @property
    def params(self) -> typing.Tuple[typing.Any, ...]:
        return self._params

    def visit_jsonpath_specification(self, jsonpath: str, params: typing.Tuple[typing.Any, ...]):
        self._sql += "jsonb_path_match(%s, '%s')" % (self._target_value_expr, jsonpath)  # jsonb_path_match_tz?
        self._params += params

    def visit_query_specification(
            self,
            query: IQueryOperator,
            aggregate_provider_accessor: typing.Callable[[], typing.Any] | None = None
    ):
        object_pattern = query_to_plain_value(query)
        self._visit_object_pattern(object_pattern, aggregate_provider_accessor)

    def _visit_object_pattern(
            self,
            object_pattern: dict,
            aggregate_provider_accessor: typing.Callable[[], typing.Any] | None = None
    ):
        if not object_pattern:
            return

        # object_pattern may not be a dict — use simple @> containment
        # (scalar value or composite object without provider metadata)
        if not isinstance(object_pattern, dict):
            self._sql += "%s @> %%s" % self._target_value_expr
            self._params += (self._encode(object_pattern),)
            return

        # Separate into simple and nested constraints
        simple_constraints = {}
        nested_constraints = {}

        for key, value in object_pattern.items():
            if isinstance(value, dict):
                nested_constraints[key] = value
            else:
                simple_constraints[key] = value

        conditions = []

        # Simple constraints: value @> '{"status": "active"}'
        if simple_constraints:
            conditions.append("%s @> %%s" % self._target_value_expr)
            self._params += (self._encode(simple_constraints),)

        # Nested constraints (dict) — check the provider type:
        # - IReferenceProvider -> FK to another aggregate -> subquery
        # - ICompositeValueProvider or other -> composite Value Object / Entity -> simple @>
        if nested_constraints and aggregate_provider_accessor is not None:
            from ascetic_ddd.faker.domain.providers.interfaces import IReferenceProvider

            aggregate_provider = aggregate_provider_accessor()
            providers = aggregate_provider.providers

            for key, nested_pattern in nested_constraints.items():
                nested_provider = providers.get(key)
                if isinstance(nested_provider, IReferenceProvider):
                    # FK to another aggregate — get the table and build a subquery
                    related_agg_provider = nested_provider.aggregate_provider
                    if hasattr(related_agg_provider, '_repository'):
                        related_table = related_agg_provider.repository.table

                        # Recursively build a subquery for the nested pattern
                        subquery_sql, subquery_params = self._build_subquery(
                            key,
                            related_table,
                            nested_pattern,
                            lambda: related_agg_provider
                        )
                        conditions.append(subquery_sql)
                        self._params += subquery_params
                else:
                    # Composite Value Object / Entity — use simple @>
                    conditions.append("%s @> %%s" % self._target_value_expr)
                    self._params += (self._encode({key: nested_pattern}),)
        elif nested_constraints:
            # No aggregate_provider_accessor — fallback to simple @>
            conditions.append("%s @> %%s" % self._target_value_expr)
            self._params += (self._encode(nested_constraints),)

        if conditions:
            self._sql += " AND ".join(conditions)

    def _build_subquery(
            self,
            fk_key: str,
            related_table: str,
            nested_pattern: dict,
            related_aggregate_provider_accessor: typing.Callable[[], typing.Any]
    ) -> tuple[str, tuple]:
        """
        Builds an EXISTS subquery for a nested constraint.

        Uses EXISTS instead of IN for better index utilization:
        - rt.value @> '{"status": "active"}' — uses GIN index
        - rt.value_id = main.value->'fk_id' — uses B-tree index (UNIQUE constraint)

        Args:
            fk_key: FK attribute name (e.g., 'fk_id')
            related_table: table of the related aggregate
            nested_pattern: nested pattern for filtering
            related_aggregate_provider_accessor: accessor for the related AggregateProvider

        Returns:
            (sql, params) — SQL condition and parameters
        """
        # Recursively process the nested pattern
        nested_visitor = PgSpecificationVisitor(target_value_expr="rt.value")
        nested_visitor._visit_object_pattern(
            nested_pattern,
            related_aggregate_provider_accessor
        )

        if nested_visitor.sql:
            # EXISTS (SELECT 1 FROM related_table rt WHERE rt.value @> ... AND rt.value_id = main.value->'fk_id')
            # fk_key is safe — it is an attribute name from the provider code
            sql = "EXISTS (SELECT 1 FROM %s rt WHERE %s AND rt.value_id = %s->'%s')" % (
                related_table,
                nested_visitor.sql,
                self._target_value_expr,
                fk_key,
            )
            return (sql, nested_visitor.params)
        else:
            return ("TRUE", tuple())

    def visit_scope_specification(self, scope: typing.Hashable):
        pass

    def visit_empty_specification(self):
        pass

    @staticmethod
    def _encode(obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            obj = dataclasses.asdict(obj)
        dumps = functools.partial(json.dumps, cls=JSONEncoder)
        return Jsonb(obj, dumps)
