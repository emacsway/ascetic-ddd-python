"""
Query merger for combining multiple queries.

Merges queries following these rules:
- EqOperator + EqOperator (same value) -> EqOperator
- EqOperator + EqOperator (different) -> DiamondUpdateConflict
- EqOperator + RelOperator -> RelOperator with id from EqOperator
- RelOperator + RelOperator -> deep merge constraints
- CompositeQuery + CompositeQuery -> merge fields
"""
import typing

from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator,
    EqOperator,
    RelOperator,
    CompositeQuery,
)
from ascetic_ddd.faker.domain.providers.exceptions import DiamondUpdateConflict

__all__ = ('QueryMerger',)


def normalize_query(op: IQueryOperator) -> IQueryOperator:
    """
    Normalize query by unwrapping redundant EqOperator wrappers.

    EqOperator(CompositeQuery({'a': EqOperator(1)})) -> CompositeQuery({'a': EqOperator(1)})

    Assumes tree is fully parsed (no raw dicts inside EqOperator).
    This ensures consistent structure for merging.
    """
    if isinstance(op, EqOperator):
        if isinstance(op.value, IQueryOperator):
            # Unwrap: EqOperator(CompositeQuery(...)) -> CompositeQuery(...)
            return normalize_query(op.value)
        return op

    if isinstance(op, RelOperator):
        normalized = {k: normalize_query(v) for k, v in op.constraints.items()}
        return RelOperator(normalized)

    if isinstance(op, CompositeQuery):
        normalized = {k: normalize_query(v) for k, v in op.fields.items()}
        return CompositeQuery(normalized)

    return op


class QueryMerger:
    """
    Merges two queries into one.

    Used when set() is called multiple times on a provider.
    Instead of replacing, it merges the queries.

    Args:
        id_attr: Name of the ID attribute for wrapping EqOperator into RelOperator.
                 Used by ReferenceProvider to place PK into $rel.id.
    """

    def __init__(self, id_attr: str = 'id'):
        self._id_attr = id_attr

    def merge(
        self,
        left: IQueryOperator | None,
        right: IQueryOperator | None,
        provider_name: str | None = None
    ) -> IQueryOperator | None:
        """
        Merge two queries.

        Args:
            left: Existing query (can be None)
            right: New query to merge (can be None)
            provider_name: Provider name for error messages

        Returns:
            Merged query

        Raises:
            DiamondUpdateConflict: When merging incompatible EqOperators
        """
        if left is None:
            return right
        if right is None:
            return left

        # Normalize only when needed for structure compatibility
        # Don't normalize when:
        # - Same type (EqOperator + EqOperator, etc.) - compare as-is
        # - EqOperator + RelOperator - EqOperator goes under $rel.id as-is
        need_normalize = (
            type(left) != type(right) and
            not (isinstance(left, EqOperator) and isinstance(right, RelOperator)) and
            not (isinstance(left, RelOperator) and isinstance(right, EqOperator))
        )
        if need_normalize:
            left = normalize_query(left)
            right = normalize_query(right)

        return self._do_merge(left, right, provider_name)

    def _do_merge(
        self,
        left: IQueryOperator,
        right: IQueryOperator,
        provider_name: str | None
    ) -> IQueryOperator:
        """Perform the actual merge."""
        # Normalize when types differ (recursive calls)
        # Skip normalization for EqOperator+RelOperator (handled specially)
        if type(left) != type(right):
            if not (
                (isinstance(left, EqOperator) and isinstance(right, RelOperator)) or
                (isinstance(left, RelOperator) and isinstance(right, EqOperator))
            ):
                left = normalize_query(left)
                right = normalize_query(right)

        # EqOperator + EqOperator
        if isinstance(left, EqOperator) and isinstance(right, EqOperator):
            return self._merge_eq_eq(left, right, provider_name)

        # RelOperator + RelOperator
        if isinstance(left, RelOperator) and isinstance(right, RelOperator):
            return self._merge_rel_rel(left, right, provider_name)

        # EqOperator + RelOperator (either order)
        if isinstance(left, EqOperator) and isinstance(right, RelOperator):
            return self._merge_eq_into_rel(left, right, provider_name)
        if isinstance(left, RelOperator) and isinstance(right, EqOperator):
            return self._merge_eq_into_rel(right, left, provider_name)

        # CompositeQuery + CompositeQuery
        if isinstance(left, CompositeQuery) and isinstance(right, CompositeQuery):
            return self._merge_composite_composite(left, right, provider_name)

        # CompositeQuery + RelOperator (either order) - wrap CompositeQuery as id constraint
        if isinstance(left, CompositeQuery) and isinstance(right, RelOperator):
            return self._merge_composite_into_rel(left, right, provider_name)
        if isinstance(left, RelOperator) and isinstance(right, CompositeQuery):
            return self._merge_composite_into_rel(right, left, provider_name)

        # EqOperator(scalar) + CompositeQuery - scalar is more specific, keep it
        if isinstance(left, EqOperator) and isinstance(right, CompositeQuery):
            return left
        if isinstance(left, CompositeQuery) and isinstance(right, EqOperator):
            return right

        raise ValueError(
            f"Cannot merge {type(left).__name__} with {type(right).__name__}"
        )

    def _merge_eq_eq(
        self,
        left: EqOperator,
        right: EqOperator,
        provider_name: str | None
    ) -> EqOperator:
        """Merge two EqOperators."""
        if left.value == right.value:
            return left

        # Different values - conflict
        raise DiamondUpdateConflict(left.value, right.value, provider_name)

    def _merge_rel_rel(
        self,
        left: RelOperator,
        right: RelOperator,
        provider_name: str | None
    ) -> RelOperator:
        """Merge two RelOperators by deep merging constraints."""
        merged_constraints: dict[str, IQueryOperator] = dict(left.constraints)

        for field, op in right.constraints.items():
            if field in merged_constraints:
                merged_constraints[field] = self._do_merge(
                    merged_constraints[field], op, provider_name
                )
            else:
                merged_constraints[field] = op

        return RelOperator(merged_constraints)

    def _merge_eq_into_rel(
        self,
        eq: EqOperator,
        rel: RelOperator,
        provider_name: str | None
    ) -> RelOperator:
        """
        Merge EqOperator into RelOperator.

        The EqOperator value is placed into $rel as the id constraint.
        """
        merged_constraints: dict[str, IQueryOperator] = dict(rel.constraints)

        if self._id_attr in merged_constraints:
            # Merge with existing id constraint
            merged_constraints[self._id_attr] = self._do_merge(
                merged_constraints[self._id_attr], eq, provider_name
            )
        else:
            # Add new id constraint
            merged_constraints[self._id_attr] = eq

        return RelOperator(merged_constraints)

    def _merge_composite_into_rel(
        self,
        composite: CompositeQuery,
        rel: RelOperator,
        provider_name: str | None
    ) -> RelOperator:
        """
        Merge CompositeQuery into RelOperator.

        The CompositeQuery is placed under $rel as the id constraint.
        """
        merged_constraints: dict[str, IQueryOperator] = dict(rel.constraints)

        if self._id_attr in merged_constraints:
            # Merge with existing id constraint
            merged_constraints[self._id_attr] = self._do_merge(
                merged_constraints[self._id_attr], composite, provider_name
            )
        else:
            # Add new id constraint
            merged_constraints[self._id_attr] = composite

        return RelOperator(merged_constraints)

    def _merge_composite_composite(
        self,
        left: CompositeQuery,
        right: CompositeQuery,
        provider_name: str | None
    ) -> CompositeQuery:
        """Merge two CompositeQueries by merging fields."""
        merged_fields: dict[str, IQueryOperator] = dict(left.fields)

        for field, op in right.fields.items():
            if field in merged_fields:
                merged_fields[field] = self._do_merge(
                    merged_fields[field], op, provider_name
                )
            else:
                merged_fields[field] = op

        return CompositeQuery(merged_fields)
