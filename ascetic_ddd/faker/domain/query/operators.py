"""
Query operators for MongoDB-like query syntax.

Operators:
- $eq: equality check
- $rel: constraints for related aggregate

Examples:
    {'$eq': 27}                                    # scalar value
    {'tenant_id': {'$eq': 15}, 'local_id': {'$eq': 27}}  # composite PK
    {'$rel': {'is_active': {'$eq': True}}}         # related aggregate criteria
"""
import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.seedwork.domain.utils.data import hashable

__all__ = (
    'IQueryOperator',
    'IQueryVisitor',
    'MergeConflict',
    'EqOperator',
    'RelOperator',
    'CompositeQuery',
)


class MergeConflict(Exception):
    """Raised when merging two operators with incompatible values."""

    def __init__(self, existing_value: typing.Any, new_value: typing.Any):
        self.existing_value = existing_value
        self.new_value = new_value
        super().__init__(f"Cannot merge {existing_value!r} with {new_value!r}")


T = typing.TypeVar('T')


class IQueryVisitor(typing.Generic[T], metaclass=ABCMeta):
    """Visitor for traversing query operator tree."""

    @abstractmethod
    def visit_eq(self, op: 'EqOperator') -> T:
        raise NotImplementedError

    @abstractmethod
    def visit_rel(self, op: 'RelOperator') -> T:
        raise NotImplementedError

    @abstractmethod
    def visit_composite(self, op: 'CompositeQuery') -> T:
        raise NotImplementedError


class IQueryOperator(metaclass=ABCMeta):
    """Base interface for all query operators."""

    @abstractmethod
    def accept(self, visitor: IQueryVisitor[T]) -> T:
        raise NotImplementedError

    @abstractmethod
    def __eq__(self, other: object) -> bool:
        raise NotImplementedError

    @abstractmethod
    def __hash__(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def __add__(self, other: 'IQueryOperator') -> 'IQueryOperator':
        raise NotImplementedError


class EqOperator(IQueryOperator):
    """
    Equality operator: {'$eq': value}

    Represents exact value match. Value can be:
    - Primitive (int, str, bool, None)
    - IQueryOperator (parsed subtree, before normalization)
    """
    __slots__ = ('value', '_hash')

    def __init__(self, value: typing.Any):
        self.value = value
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_eq(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EqOperator):
            return False
        return self.value == other.value

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(('$eq', hashable(self.value)))
        return self._hash

    def __add__(self, other: 'EqOperator') -> 'EqOperator':
        if not isinstance(other, EqOperator):
            return NotImplemented
        if self.value == other.value:
            return self
        raise MergeConflict(self.value, other.value)

    def __repr__(self) -> str:
        return f"EqOperator({self.value!r})"


class RelOperator(IQueryOperator):
    """
    Relation operator: {'$rel': {'field': {'$eq': value}, ...}}

    Represents constraints on a related aggregate.
    Used by ReferenceProvider to specify criteria for the referenced aggregate.
    """
    __slots__ = ('constraints', '_hash')

    def __init__(self, constraints: dict[str, IQueryOperator]):
        self.constraints = constraints
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_rel(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RelOperator):
            return False
        return self.constraints == other.constraints

    def __hash__(self) -> int:
        if self._hash is None:
            items = tuple(sorted((k, hash(v)) for k, v in self.constraints.items()))
            self._hash = hash(('$rel', items))
        return self._hash

    def __add__(self, other: 'RelOperator') -> 'RelOperator':
        if not isinstance(other, RelOperator):
            return NotImplemented
        merged: dict[str, IQueryOperator] = dict(self.constraints)
        for field, op in other.constraints.items():
            if field in merged:
                merged[field] = merged[field] + op
            else:
                merged[field] = op
        return RelOperator(merged)

    def __repr__(self) -> str:
        return f"RelOperator({self.constraints!r})"


class CompositeQuery(IQueryOperator):
    """
    Composite query: {'field1': op1, 'field2': op2, ...}

    Represents a query with multiple field constraints.
    Used for composite primary keys or multi-field criteria.
    """
    __slots__ = ('fields', '_hash')

    def __init__(self, fields: dict[str, IQueryOperator]):
        self.fields = fields
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_composite(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CompositeQuery):
            return False
        return self.fields == other.fields

    def __hash__(self) -> int:
        if self._hash is None:
            items = tuple(sorted((k, hash(v)) for k, v in self.fields.items()))
            self._hash = hash(('composite', items))
        return self._hash

    def __add__(self, other: 'CompositeQuery') -> 'CompositeQuery':
        if not isinstance(other, CompositeQuery):
            return NotImplemented
        merged: dict[str, IQueryOperator] = dict(self.fields)
        for field, op in other.fields.items():
            if field in merged:
                merged[field] = merged[field] + op
            else:
                merged[field] = op
        return CompositeQuery(merged)

    def __repr__(self) -> str:
        return f"CompositeQuery({self.fields!r})"
