"""
EvaluateWalker for checking if an object matches query criteria.

Decoupled from providers/repositories via IObjectResolver interface,
similar to IRelationResolver in relation_resolver.py.
"""
import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, IQueryVisitor, EqOperator, ComparisonOperator, InOperator,
    IsNullOperator, AndOperator, OrOperator, RelOperator, CompositeQuery
)

__all__ = ('IObjectResolver', 'EvaluateWalker', 'EvaluateVisitor')


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


class EvaluateWalker:
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

        if isinstance(query, IsNullOperator):
            return (state is None) == query.value

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
                nested = EvaluateWalker(nested_resolver)
                return await nested.evaluate(session, query.query, foreign_state)
            # RelOperator without field context — delegate to inner query
            return await self.evaluate(session, query.query, state)

        return False

    def evaluate_sync(
            self,
            query: IQueryOperator,
            state: typing.Any,
            _field_context: tuple[str, typing.Any] | None = None,
    ) -> bool:
        """Sync evaluation. Does not support RelOperator with resolver.

        _field_context is (field_name, fk_value) — propagated through And/Or
        so that nested RelOperator can resolve relations.
        """
        if isinstance(query, EqOperator):
            return state == query.value

        if isinstance(query, ComparisonOperator):
            return self._compare(query.op, state, query.value)

        if isinstance(query, InOperator):
            return state in query.values

        if isinstance(query, IsNullOperator):
            return (state is None) == query.value

        if isinstance(query, AndOperator):
            for operand in query.operands:
                if not self.evaluate_sync(operand, state, _field_context):
                    return False
            return True

        if isinstance(query, OrOperator):
            for operand in query.operands:
                if self.evaluate_sync(operand, state, _field_context):
                    return True
            return False

        if isinstance(query, CompositeQuery):
            return self._evaluate_composite_sync(query, state)

        if isinstance(query, RelOperator):
            # RelOperator without field context — delegate to inner query
            return self.evaluate_sync(query.query, state)

        return False

    def _evaluate_composite_sync(
            self,
            query: CompositeQuery,
            state: typing.Any
    ) -> bool:
        """Evaluate composite query against dict state (sync)."""
        if not isinstance(state, dict):
            return False
        for field, field_op in query.fields.items():
            field_value = state.get(field)
            if not self._evaluate_field_sync(field, field_op, field_value):
                return False
        return True

    def _evaluate_field_sync(
            self,
            field: str,
            field_op: IQueryOperator,
            field_value: typing.Any
    ) -> bool:
        """Evaluate a single field (sync). RelOperator delegates to inner query."""
        if isinstance(field_op, RelOperator):
            # No async resolver — delegate to inner query with field_value as state
            return self.evaluate_sync(field_op.query, field_value)

        return self.evaluate_sync(
            field_op, field_value, _field_context=(field, field_value)
        )

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
            nested = EvaluateWalker(nested_resolver)
            return await nested.evaluate(session, field_op.query, foreign_state)

        # Regular operator — pass field context for nested RelOperator inside Or/And
        return await self.evaluate(
            session, field_op, field_value, _field_context=(field, field_value)
        )


T = typing.TypeVar('T')


class EvaluateVisitor(IQueryVisitor[typing.Awaitable[bool]]):
    """
    Visitor-based evaluator: checks if an object state matches query criteria.

    Implements IQueryVisitor[Awaitable[bool]] with double dispatch via accept().
    State is carried in the instance; recursion creates new instances.

    Usage:
        evaluator = EvaluateVisitor(state, session, object_resolver)
        result = await query.accept(evaluator)
    """

    __slots__ = ('_state', '_session', '_object_resolver', '_field_context')

    def __init__(
            self,
            state: typing.Any,
            session: typing.Any,
            object_resolver: IObjectResolver | None = None,
            _field_context: tuple[str, typing.Any] | None = None,
    ):
        self._state = state
        self._session = session
        self._object_resolver = object_resolver
        self._field_context = _field_context

    def _with_state(
            self,
            state: typing.Any,
            object_resolver: IObjectResolver | None = None,
            _field_context: tuple[str, typing.Any] | None = None,
    ) -> 'EvaluateVisitor':
        return EvaluateVisitor(
            state,
            self._session,
            object_resolver if object_resolver is not None else self._object_resolver,
            _field_context,
        )

    async def visit_eq(self, op: EqOperator) -> bool:
        return self._state == op.value

    async def visit_comparison(self, op: ComparisonOperator) -> bool:
        if op.op == '$ne':
            return self._state != op.value
        if op.op == '$gt':
            return self._state > op.value
        if op.op == '$gte':
            return self._state >= op.value
        if op.op == '$lt':
            return self._state < op.value
        if op.op == '$lte':
            return self._state <= op.value
        return False

    async def visit_in(self, op: InOperator) -> bool:
        return self._state in op.values

    async def visit_is_null(self, op: IsNullOperator) -> bool:
        return (self._state is None) == op.value

    async def visit_and(self, op: AndOperator) -> bool:
        for operand in op.operands:
            evaluator = self._with_state(
                self._state, _field_context=self._field_context
            )
            if not await operand.accept(evaluator):
                return False
        return True

    async def visit_or(self, op: OrOperator) -> bool:
        for operand in op.operands:
            evaluator = self._with_state(
                self._state, _field_context=self._field_context
            )
            if await operand.accept(evaluator):
                return True
        return False

    async def visit_rel(self, op: RelOperator) -> bool:
        if self._field_context is not None and self._object_resolver is not None:
            field, fk_value = self._field_context
            foreign_state, nested_resolver = await self._object_resolver.resolve(
                self._session, field, fk_value
            )
            if foreign_state is None:
                return False
            nested = self._with_state(foreign_state, object_resolver=nested_resolver)
            return await op.query.accept(nested)
        # RelOperator without field context — delegate to inner query
        return await op.query.accept(self)

    async def visit_composite(self, op: CompositeQuery) -> bool:
        if not isinstance(self._state, dict):
            return False
        for field, field_op in op.fields.items():
            field_value = self._state.get(field)
            # RelOperator on a field — resolve relation directly
            if isinstance(field_op, RelOperator) and self._object_resolver is not None:
                foreign_state, nested_resolver = await self._object_resolver.resolve(
                    self._session, field, field_value
                )
                if foreign_state is None:
                    return False
                nested = self._with_state(foreign_state, object_resolver=nested_resolver)
                if not await field_op.query.accept(nested):
                    return False
            else:
                # Pass field context for nested RelOperator inside Or/And
                evaluator = self._with_state(
                    field_value, _field_context=(field, field_value)
                )
                if not await field_op.accept(evaluator):
                    return False
        return True
