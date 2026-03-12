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

    def resolve(self, field: str | None) -> RelationInfo | None:
        aggregate_provider = self._aggregate_provider_accessor()

        if field is None:
            # Top-level: resolve the root aggregate directly
            related_provider = aggregate_provider
        else:
            provider = aggregate_provider.providers.get(field)
            if not isinstance(provider, IReferenceProvider):
                return None
            related_provider = provider.aggregate_provider

        if not hasattr(related_provider, 'repository'):
            return None

        return RelationInfo(
            table=related_provider.repository.table,
            pk_field='value_id',
            nested_resolver=ProviderRelationResolver(lambda: related_provider),
        )

    def descend(self, field: str) -> 'ProviderRelationResolver | None':
        aggregate_provider = self._aggregate_provider_accessor()
        provider = aggregate_provider.providers.get(field)
        if provider is None:
            return None
        if isinstance(provider, IReferenceProvider):
            id_provider = provider.aggregate_provider.id_provider
            if hasattr(id_provider, 'providers'):
                return ProviderRelationResolver(lambda p=id_provider: p)
            return None
        if hasattr(provider, 'providers'):
            return ProviderRelationResolver(lambda p=provider: p)
        return None
