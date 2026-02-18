"""
Relation resolver interface and adapter for PgQueryCompiler.

IRelationResolver abstracts away provider/repository details,
allowing PgQueryCompiler to resolve field names to SQL table info.
"""
import typing
from abc import ABCMeta, abstractmethod

from ascetic_ddd.faker.domain.providers.interfaces import IReferenceProvider

__all__ = ('IRelationResolver', 'ProviderRelationResolver')


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


class ProviderRelationResolver(IRelationResolver):
    """Adapter: wraps AggregateProvider to implement IRelationResolver."""

    __slots__ = ('_aggregate_provider_accessor',)

    def __init__(self, aggregate_provider_accessor: typing.Callable[[], typing.Any]):
        self._aggregate_provider_accessor = aggregate_provider_accessor

    def resolve(self, field: str) -> RelationInfo | None:
        aggregate_provider = self._aggregate_provider_accessor()
        provider = aggregate_provider.providers.get(field)

        if not isinstance(provider, IReferenceProvider):
            return None

        related_provider = provider.aggregate_provider

        if not hasattr(related_provider, '_repository'):
            return None

        related_table = related_provider._repository.table
        pk_field = 'value_id'

        nested_resolver = ProviderRelationResolver(lambda rp=related_provider: rp)

        return RelationInfo(
            table=related_table,
            pk_field=pk_field,
            nested_resolver=nested_resolver,
        )
