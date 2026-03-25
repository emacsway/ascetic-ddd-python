import typing

from ascetic_ddd.faker.domain.query.operators import IQueryOperator
from ascetic_ddd.faker.domain.specification.interfaces import ISpecificationVisitor
from ascetic_ddd.faker.infrastructure.query.pg_query_compiler import PgQueryCompiler
from ascetic_ddd.faker.infrastructure.specification.relation_resolver import ProviderRelationResolver

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
        relation_resolver = None
        if aggregate_provider_accessor is not None:
            relation_resolver = ProviderRelationResolver(aggregate_provider_accessor)
        compiler = PgQueryCompiler(
            target_value_expr=self._target_value_expr,
            relation_resolver=relation_resolver,
        )
        sql, params = compiler.compile(query)
        self._sql += sql
        self._params += params

    def visit_empty_specification(self):
        pass
