import typing

from ascetic_ddd.faker.domain.providers.interfaces import (
    IAggregateProvider, IReferenceProvider, ICompositeValueProvider,
)
from ascetic_ddd.session.interfaces import ISession


__all__ = ('ProviderChangeManager',)


class ProviderChangeManager:
    """
    Mediator that controls populate() invocation order across the
    provider network using topological sort (Kahn's algorithm).

    Solves the diamond problem: when the same AggregateProvider is
    reachable via multiple paths, populate() is called exactly once
    and only after all dependencies are populated.

    Based on GoF DAGChangeManager (collectAffected + topoSort).
    """

    def _collect_providers(
            self,
            provider: IAggregateProvider,
            visited: dict[int, IAggregateProvider],
            edges: list[tuple[int, int]],
    ) -> None:
        """
        DFS: collect all reachable AggregateProviders and dependency edges.

        An edge (dep_id, provider_id) means dep must be populated before provider.
        """
        provider_id = id(provider)
        if provider_id in visited:
            return
        visited[provider_id] = provider
        self._find_references(provider, provider_id, visited, edges)

    def _find_references(
            self,
            provider: typing.Any,
            dependent_id: int,
            visited: dict[int, IAggregateProvider],
            edges: list[tuple[int, int]],
    ) -> None:
        """
        Walk a provider tree to find all ReferenceProvider dependencies.

        Recurses into ICompositeValueProvider (CompositeValueProvider,
        EntityProvider) to find nested ReferenceProviders.
        """
        if isinstance(provider, IReferenceProvider):
            dep_provider = provider.aggregate_provider
            dependency_id = id(dep_provider)
            edges.append((dependency_id, dependent_id))  # parent, child
            self._collect_providers(dep_provider, visited, edges)
            return

        if isinstance(provider, ICompositeValueProvider):
            for attr, nested in provider.providers.items():
                self._find_references(nested, dependent_id, visited, edges)

    def _topo_sort(
            self,
            visited: dict[int, IAggregateProvider],
            edges: list[tuple[int, int]],
    ) -> list[IAggregateProvider]:
        """Kahn's algorithm: topological sort of AggregateProviders."""
        in_degree: dict[int, int] = {pid: 0 for pid in visited}
        adjacency: dict[int, list[int]] = {pid: [] for pid in visited}

        for dependency_id, dependent_id in edges:  # parent, child
            if dependency_id in visited and dependent_id in visited:
                in_degree[dependent_id] += 1
                adjacency[dependency_id].append(dependent_id)

        queue: list[int] = [pid for pid, deg in in_degree.items() if deg == 0]
        sorted_: list[IAggregateProvider] = []

        while queue:
            pid = queue.pop(0)
            sorted_.append(visited[pid])
            for dependent_id in adjacency[pid]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        return sorted_

    async def populate(self, session: ISession, root_provider: IAggregateProvider) -> None:
        """
        Populate the provider network in topological order.

        Each AggregateProvider's populate() is called exactly once.
        Dependencies are populated before dependents.
        """
        visited: dict[int, IAggregateProvider] = {}
        edges: list[tuple[int, int]] = []
        self._collect_providers(root_provider, visited, edges)

        sorted_providers = self._topo_sort(visited, edges)

        for provider in sorted_providers:
            await provider.populate(session)
