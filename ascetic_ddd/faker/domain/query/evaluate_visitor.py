"""
EvaluateVisitor for checking if an object matches query criteria.

Decoupled from providers/repositories via IObjectResolver interface,
similar to IRelationResolver in relation_resolver.py.
"""
import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, EqOperator, ComparisonOperator, InOperator,
    AndOperator, OrOperator, RelOperator, CompositeQuery
)

__all__ = ('IObjectResolver', 'EvaluateVisitor')


class IObjectResolver(metaclass=ABCMeta):
    """Resolves a relation field to foreign object state for evaluation."""

    @abstractmethod
    async def resolve(
            self,
            session: typing.Any,
            field: str,
            fk_value: typing.Any
    ) -> tuple[dict | None, 'IObjectResolver | None']:
        """
        Resolve a relation field to foreign object state.

        Returns (foreign_state_dict, nested_resolver) if found,
        (None, None) if field is not a relation or object not found.
        """
        raise NotImplementedError


class EvaluateVisitor:
    """
    Evaluates whether an object state matches query criteria.

    Supports all query operators. Uses IObjectResolver for
    resolving RelOperator fields to foreign object state.
    """

    def __init__(self, object_resolver: IObjectResolver | None = None):
        self._object_resolver = object_resolver

    async def evaluate(
            self,
            session: typing.Any,
            query: IQueryOperator,
            state: typing.Any,
            _field_context: tuple[str, typing.Any] | None = None,
    ) -> bool:
        """Check if state matches query.

        _field_context is (field_name, fk_value) — propagated through And/Or
        so that nested RelOperator can resolve relations.
        """
        if isinstance(query, EqOperator):
            return state == query.value

        if isinstance(query, ComparisonOperator):
            return self._compare(query.op, state, query.value)

        if isinstance(query, InOperator):
            return state in query.values

        if isinstance(query, AndOperator):
            for operand in query.operands:
                if not await self.evaluate(session, operand, state, _field_context):
                    return False
            return True

        if isinstance(query, OrOperator):
            for operand in query.operands:
                if await self.evaluate(session, operand, state, _field_context):
                    return True
            return False

        if isinstance(query, CompositeQuery):
            return await self._evaluate_composite(session, query, state)

        if isinstance(query, RelOperator):
            if _field_context is not None and self._object_resolver is not None:
                field, fk_value = _field_context
                foreign_state, nested_resolver = await self._object_resolver.resolve(
                    session, field, fk_value
                )
                if foreign_state is None:
                    return False
                nested = EvaluateVisitor(nested_resolver)
                return await nested.evaluate(session, query.query, foreign_state)
            # RelOperator without field context — delegate to inner query
            return await self.evaluate(session, query.query, state)

        return False

    def _compare(self, op: str, actual: typing.Any, expected: typing.Any) -> bool:
        """Evaluate comparison operator."""
        if op == '$ne':
            return actual != expected
        if op == '$gt':
            return actual > expected
        if op == '$gte':
            return actual >= expected
        if op == '$lt':
            return actual < expected
        if op == '$lte':
            return actual <= expected
        return False

    async def _evaluate_composite(
            self,
            session: typing.Any,
            query: CompositeQuery,
            state: typing.Any
    ) -> bool:
        """Evaluate composite query against dict state."""
        if not isinstance(state, dict):
            return False
        for field, field_op in query.fields.items():
            field_value = state.get(field)
            if not await self._evaluate_field(session, field, field_op, field_value):
                return False
        return True

    async def _evaluate_field(
            self,
            session: typing.Any,
            field: str,
            field_op: IQueryOperator,
            field_value: typing.Any
    ) -> bool:
        """Evaluate a single field, resolving relations via IObjectResolver."""
        # RelOperator on a field — resolve relation
        if isinstance(field_op, RelOperator) and self._object_resolver is not None:
            foreign_state, nested_resolver = await self._object_resolver.resolve(
                session, field, field_value
            )
            if foreign_state is None:
                return False
            nested = EvaluateVisitor(nested_resolver)
            return await nested.evaluate(session, field_op.query, foreign_state)

        # Regular operator — pass field context for nested RelOperator inside Or/And
        return await self.evaluate(
            session, field_op, field_value, _field_context=(field, field_value)
        )
