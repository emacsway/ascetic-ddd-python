"""
Provider-based object resolver for EvaluateWalker.

Adapts AggregateProvider to IObjectResolver interface,
similar to ProviderRelationResolver in relation_resolver.py.
"""
import typing

from ascetic_ddd.faker.domain.providers.interfaces import IReferenceProvider
from ascetic_ddd.faker.domain.query.evaluate_visitor import IObjectResolver

__all__ = ('ProviderObjectResolver',)


class ProviderObjectResolver(IObjectResolver):
    """Adapter: wraps AggregateProvider to implement IObjectResolver."""

    __slots__ = ('_aggregate_provider_accessor',)

    def __init__(self, aggregate_provider_accessor: typing.Callable[[], typing.Any]):
        self._aggregate_provider_accessor = aggregate_provider_accessor

    async def resolve(
            self,
            session: typing.Any,
            field: str | None,
            fk_value: typing.Any
    ) -> tuple[dict | None, 'IObjectResolver | None']:

        if fk_value is None:
            return None, None

        aggregate_provider = self._aggregate_provider_accessor()

        if field is None:
            related_provider = aggregate_provider
        else:
            provider = aggregate_provider.providers.get(field)
            if not isinstance(provider, IReferenceProvider):
                return None, None
            related_provider = provider.aggregate_provider

        obj = await related_provider.repository.get(session, fk_value)

        if obj is None:
            return None, None

        state = related_provider.export(obj)
        nested = ProviderObjectResolver(lambda: related_provider)
        return state, nested

    def descend(self, field: str) -> 'ProviderObjectResolver | None':
        aggregate_provider = self._aggregate_provider_accessor()
        provider = aggregate_provider.providers.get(field)
        if provider is None:
            return None
        if isinstance(provider, IReferenceProvider):
            id_provider = provider.aggregate_provider.id_provider
            if hasattr(id_provider, 'providers'):
                return ProviderObjectResolver(lambda p=id_provider: p)
            return None
        if hasattr(provider, 'providers'):
            return ProviderObjectResolver(lambda p=provider: p)
        return None
