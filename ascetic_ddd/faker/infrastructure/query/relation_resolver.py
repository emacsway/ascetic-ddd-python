"""
Relation resolver interface and adapter for PgQueryCompiler.

IRelationResolver abstracts away provider/repository details,
allowing PgQueryCompiler to resolve field names to SQL table info.
"""
import typing

from ascetic_ddd.faker.domain.providers.interfaces import IReferenceProvider
from ascetic_ddd.faker.infrastructure.query.pg_query_compiler import RelationInfo, IRelationResolver


__all__ = ('ProviderRelationResolver',)


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

        related_table = related_provider.repository.table
        pk_field = 'value_id'

        nested_resolver = ProviderRelationResolver(lambda: related_provider)

        return RelationInfo(
            table=related_table,
            pk_field=pk_field,
            nested_resolver=nested_resolver,
        )
