"""
Query operators for MongoDB-like query syntax.

Operators:
- $eq: equality check
- $ne: not equal
- $gt, $gte, $lt, $lte: comparison operators
- $in: value in list
- $is_null: null check
- $not: logical negation
- $any: existential quantifier (at least one array element matches)
- $all: universal quantifier (every array element matches)
- $len: array length predicate
- $rel: constraints for related aggregate
- $or: logical OR of expressions

Multiple operators at same level are implicit AND:
    {'$gt': 5, '$lt': 10}  -> AndOperator((ComparisonOperator('$gt', 5), ComparisonOperator('$lt', 10)))

Examples:
    {'$eq': 27}                                    # scalar value
    {'$ne': 'deleted'}                             # not equal
    {'$gt': 5, '$lt': 10}                          # range (implicit AND)
    {'$in': ['active', 'pending']}                 # value in list
    {'$is_null': True}                             # null check
    {'$is_null': False}                            # not null check
    {'status': {'$not': {'$eq': 'deleted'}}}       # negation
    {'items': {'$any': {'status': {'$eq': 'shipped'}}}}  # any element matches
    {'items': {'$all': {'status': {'$eq': 'active'}}}}   # all elements match
    {'items': {'$len': {'$gt': 2}}}                # array length predicate
    {'tenant_id': {'$eq': 15}, 'local_id': {'$eq': 27}}  # composite PK
    {'$rel': {'is_active': {'$eq': True}}}         # related aggregate criteria
    {'$or': [{'status': {'$eq': 'active'}}, {'status': {'$eq': 'pending'}}]}
"""
import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.seedwork.domain.utils.data import hashable

__all__ = (
    'IQueryOperator',
    'IQueryVisitor',
    'MergeConflict',
    'EqOperator',
    'ComparisonOperator',
    'InOperator',
    'IsNullOperator',
    'NotOperator',
    'AnyElementOperator',
    'AllElementsOperator',
    'LenOperator',
    'AndOperator',
    'OrOperator',
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
    def visit_comparison(self, op: 'ComparisonOperator') -> T:
        raise NotImplementedError

    @abstractmethod
    def visit_in(self, op: 'InOperator') -> T:
        raise NotImplementedError

    @abstractmethod
    def visit_is_null(self, op: 'IsNullOperator') -> T:
        raise NotImplementedError

    @abstractmethod
    def visit_and(self, op: 'AndOperator') -> T:
        raise NotImplementedError

    @abstractmethod
    def visit_or(self, op: 'OrOperator') -> T:
        raise NotImplementedError

    @abstractmethod
    def visit_not(self, op: 'NotOperator') -> T:
        raise NotImplementedError

    @abstractmethod
    def visit_any_element(self, op: 'AnyElementOperator') -> T:
        raise NotImplementedError

    @abstractmethod
    def visit_all_elements(self, op: 'AllElementsOperator') -> T:
        raise NotImplementedError

    @abstractmethod
    def visit_len(self, op: 'LenOperator') -> T:
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

    def __add__(self, other: 'IQueryOperator') -> 'EqOperator':
        if not isinstance(other, EqOperator):
            return NotImplemented
        if self.value == other.value:
            return self
        raise MergeConflict(self.value, other.value)

    def __repr__(self) -> str:
        return f"EqOperator({self.value!r})"


class ComparisonOperator(IQueryOperator):
    """
    Comparison operator: {'$ne': value}, {'$gt': value}, {'$gte': value}, {'$lt': value}, {'$lte': value}

    Supported ops: '$ne', '$gt', '$gte', '$lt', '$lte'
    """
    SUPPORTED_OPS = frozenset(('$ne', '$gt', '$gte', '$lt', '$lte'))

    __slots__ = ('op', 'value', '_hash')

    def __init__(self, op: str, value: typing.Any):
        self.op = op
        self.value = value
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_comparison(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ComparisonOperator):
            return False
        return self.op == other.op and self.value == other.value

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash((self.op, hashable(self.value)))
        return self._hash

    def __add__(self, other: 'IQueryOperator') -> 'ComparisonOperator':
        if not isinstance(other, ComparisonOperator):
            return NotImplemented
        if self.op == other.op and self.value == other.value:
            return self
        raise MergeConflict((self.op, self.value), (other.op, other.value))

    def __repr__(self) -> str:
        return f"ComparisonOperator({self.op!r}, {self.value!r})"


class OrOperator(IQueryOperator):
    """
    Logical OR: {'$or': [expr1, expr2, ...]}

    Each operand is an IQueryOperator.
    """
    __slots__ = ('operands', '_hash')

    def __init__(self, operands: tuple[IQueryOperator, ...]):
        self.operands = operands
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_or(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OrOperator):
            return False
        return self.operands == other.operands

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(('$or', tuple(hash(op) for op in self.operands)))
        return self._hash

    def __add__(self, other: 'IQueryOperator') -> 'OrOperator':
        if not isinstance(other, OrOperator):
            return NotImplemented
        if self.operands == other.operands:
            return self
        raise MergeConflict(self.operands, other.operands)

    def __repr__(self) -> str:
        return f"OrOperator({self.operands!r})"


class InOperator(IQueryOperator):
    """
    In operator: {'$in': [value1, value2, ...]}

    Represents value membership check.
    """
    __slots__ = ('values', '_hash')

    def __init__(self, values: tuple[typing.Any, ...]):
        self.values = values
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_in(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InOperator):
            return False
        return self.values == other.values

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(('$in', tuple(hashable(v) for v in self.values)))
        return self._hash

    def __add__(self, other: 'IQueryOperator') -> 'InOperator':
        if not isinstance(other, InOperator):
            return NotImplemented
        if self.values == other.values:
            return self
        raise MergeConflict(self.values, other.values)

    def __repr__(self) -> str:
        return f"InOperator({self.values!r})"


class IsNullOperator(IQueryOperator):
    """
    Null check operator: {'$is_null': True} or {'$is_null': False}

    When value=True, matches None values.
    When value=False, matches non-None values.
    """
    __slots__ = ('value', '_hash')

    def __init__(self, value: bool):
        self.value = value
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_is_null(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IsNullOperator):
            return False
        return self.value == other.value

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(('$is_null', self.value))
        return self._hash

    def __add__(self, other: 'IQueryOperator') -> 'IsNullOperator':
        if not isinstance(other, IsNullOperator):
            return NotImplemented
        if self.value == other.value:
            return self
        raise MergeConflict(self.value, other.value)

    def __repr__(self) -> str:
        return "IsNullOperator(%r)" % self.value


class NotOperator(IQueryOperator):
    """
    Logical NOT: {'$not': expr}

    Negates the result of the inner operator.
    """
    __slots__ = ('operand', '_hash')

    def __init__(self, operand: IQueryOperator):
        self.operand = operand
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_not(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NotOperator):
            return False
        return self.operand == other.operand

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(('$not', hash(self.operand)))
        return self._hash

    def __add__(self, other: 'IQueryOperator') -> 'NotOperator':
        if not isinstance(other, NotOperator):
            return NotImplemented
        if self.operand == other.operand:
            return self
        raise MergeConflict(self.operand, other.operand)

    def __repr__(self) -> str:
        return "NotOperator(%r)" % self.operand


class AnyElementOperator(IQueryOperator):
    """
    Existential quantifier: {'$any': expr}

    At least one array element matches the inner query.
    """
    __slots__ = ('query', '_hash')

    def __init__(self, query: IQueryOperator):
        self.query = query
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_any_element(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AnyElementOperator):
            return False
        return self.query == other.query

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(('$any', hash(self.query)))
        return self._hash

    def __add__(self, other: 'IQueryOperator') -> 'AnyElementOperator':
        if not isinstance(other, AnyElementOperator):
            return NotImplemented
        if self.query == other.query:
            return self
        raise MergeConflict(self.query, other.query)

    def __repr__(self) -> str:
        return "AnyElementOperator(%r)" % self.query


class AllElementsOperator(IQueryOperator):
    """
    Universal quantifier: {'$all': expr}

    Every array element matches the inner query.
    """
    __slots__ = ('query', '_hash')

    def __init__(self, query: IQueryOperator):
        self.query = query
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_all_elements(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AllElementsOperator):
            return False
        return self.query == other.query

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(('$all', hash(self.query)))
        return self._hash

    def __add__(self, other: 'IQueryOperator') -> 'AllElementsOperator':
        if not isinstance(other, AllElementsOperator):
            return NotImplemented
        if self.query == other.query:
            return self
        raise MergeConflict(self.query, other.query)

    def __repr__(self) -> str:
        return "AllElementsOperator(%r)" % self.query


class LenOperator(IQueryOperator):
    """
    Array length predicate: {'$len': expr}

    Applies the inner query (e.g. ComparisonOperator) to the array length.
    """
    __slots__ = ('query', '_hash')

    def __init__(self, query: IQueryOperator):
        self.query = query
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_len(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LenOperator):
            return False
        return self.query == other.query

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(('$len', hash(self.query)))
        return self._hash

    def __add__(self, other: 'IQueryOperator') -> 'LenOperator':
        if not isinstance(other, LenOperator):
            return NotImplemented
        if self.query == other.query:
            return self
        raise MergeConflict(self.query, other.query)

    def __repr__(self) -> str:
        return "LenOperator(%r)" % self.query


class AndOperator(IQueryOperator):
    """
    Implicit AND of operators at the same level.

    Created by parser when multiple operators appear at the same level:
        {'$gt': 5, '$lt': 10} -> AndOperator((ComparisonOperator('$gt', 5), ComparisonOperator('$lt', 10)))

    Not exposed as '$and' in query syntax.
    """
    __slots__ = ('operands', '_hash')

    def __init__(self, operands: tuple[IQueryOperator, ...]):
        self.operands = operands
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_and(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AndOperator):
            return False
        return self.operands == other.operands

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(('$and', tuple(hash(op) for op in self.operands)))
        return self._hash

    def __add__(self, other: 'IQueryOperator') -> 'AndOperator':
        if not isinstance(other, AndOperator):
            return NotImplemented
        if self.operands == other.operands:
            return self
        raise MergeConflict(self.operands, other.operands)

    def __repr__(self) -> str:
        return f"AndOperator({self.operands!r})"


class RelOperator(IQueryOperator):
    """
    Relation operator: {'$rel': {'field': {'$eq': value}, ...}}

    Represents constraints on a related aggregate.
    Used by ReferenceProvider to specify criteria for the referenced aggregate.
    Wraps a CompositeQuery with the semantic meaning "these constraints
    are for a related aggregate, not for the current one".
    """
    __slots__ = ('query', '_hash')

    def __init__(self, query: 'CompositeQuery'):
        self.query = query
        self._hash: int | None = None

    def accept(self, visitor: IQueryVisitor[T]) -> T:
        return visitor.visit_rel(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RelOperator):
            return False
        return self.query == other.query

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(('$rel', hash(self.query)))
        return self._hash

    def __add__(self, other: 'IQueryOperator') -> 'RelOperator':
        if not isinstance(other, RelOperator):
            return NotImplemented
        return RelOperator(self.query + other.query)

    def __repr__(self) -> str:
        return f"RelOperator({self.query!r})"


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

    def __add__(self, other: 'IQueryOperator') -> 'CompositeQuery':
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
