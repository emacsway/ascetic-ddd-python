"""
Provider-based object resolver for EvaluateWalker.

Adapts AggregateProvider to IObjectResolver interface,
similar to ProviderRelationResolver in relation_resolver.py.
"""
import typing

from ascetic_ddd.faker.domain.query.evaluate_visitor import IObjectResolver

__all__ = ('RepositoryObjectResolver',)


class RepositoryObjectResolver(IObjectResolver):
    """Adapter: wraps AggregateProvider to implement IObjectResolver."""

    __slots__ = ('_aggregate_provider_accessor',)

    def __init__(self, aggregate_provider_accessor: typing.Callable[[], typing.Any]):
        self._aggregate_provider_accessor = aggregate_provider_accessor

    async def resolve(
            self,
            session: typing.Any,
            field: str,
            fk_value: typing.Any
    ) -> tuple[dict | None, 'IObjectResolver | None']:
        from ascetic_ddd.faker.domain.providers.interfaces import IReferenceProvider

        aggregate_provider = self._aggregate_provider_accessor()
        provider = aggregate_provider.providers.get(field)

        if not isinstance(provider, IReferenceProvider):
            return None, None

        if fk_value is None:
            return None, None

        related_provider = provider.aggregate_provider
        obj = await related_provider._repository.get(session, fk_value)

        if obj is None:
            return None, None

        state = related_provider._output_exporter(obj)
        nested = RepositoryObjectResolver(lambda rp=related_provider: rp)
        return state, nested
