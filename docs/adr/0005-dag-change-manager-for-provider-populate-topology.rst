ADR-0005: DAG Change Manager for Provider Populate Topology
============================================================

.. index:: ADR; DAG change manager, DAG, topological sort, populate, diamond problem, ChangeManager, Mediator

Status
------
Accepted

Context
-------

ADR-0004 addressed the diamond problem in provider topology by validating
``require()`` against already-created state. That fix prevents conflicts
**after** an aggregate has been created, but does not control the **order** in
which ``populate()`` is called across the provider network.

Current approach: recursive DFS
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Currently ``populate()`` works via recursive depth-first traversal. Each
provider calls ``populate()`` on its dependencies from within its own
``populate()``::

    BookProvider.populate()
      +-- author_id (ReferenceProvider) --> AuthorProvider.populate()
      |     +-- tenant_id (ReferenceProvider) --> TenantProvider.populate()
      +-- publisher_id (ReferenceProvider) --> PublisherProvider.populate()
            +-- tenant_id (ReferenceProvider) --> TenantProvider.populate()  <-- diamond

Protection against double invocation relies on:

1. ``is_complete()`` guard at the top of each ``populate()`` -- if the provider
   is already populated, the repeated call is a no-op.
2. ``DiamondUpdateConflict`` exception in ``require()`` when new criteria
   conflict with an already-established state.
3. Repository lookup in ``AggregateProvider.populate()`` -- if the ID is already
   known, the aggregate is loaded from the repository instead of being created
   again.

Problems with the recursive approach
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. **Populate order depends on declaration order.** The iteration order of
   ``self.providers`` (a dict built from class annotations) determines which
   path reaches a shared dependency first. The winning path populates the
   provider; subsequent paths see ``is_complete() == True`` and skip. If the
   paths carry **different criteria**, the second path may either silently accept
   a foreign result or raise ``DiamondUpdateConflict``.

2. **Criteria may arrive after populate.** In a diamond, ``require()`` from
   path 2 may arrive **after** ``populate()`` from path 1 has already created
   the aggregate. ADR-0004's validation-instead-of-reset fix handles this, but
   the root cause -- uncontrolled traversal order -- remains.

3. **No single point of control.** Each provider independently decides when to
   call ``populate()`` on its dependencies. There is no centralized view of the
   dependency graph, making it difficult to reason about ordering guarantees or
   to detect cycles.

GoF DAGChangeManager
^^^^^^^^^^^^^^^^^^^^^

The Gang of Four book describes a ``DAGChangeManager`` (Mediator + Observer)
for propagating changes through a directed acyclic graph of dependencies. The
key algorithms are:

- **collectAffected(subject, visited)** -- DFS traversal that collects all
  reachable observers into a set (deduplication via visited map). Each observer
  is collected exactly once regardless of how many paths lead to it.

- **topoSort(affected)** -- Kahn's algorithm. Computes in-degree for each
  affected node, starts from nodes with zero in-degree, and processes nodes
  in topological order. Guarantees: (a) each node is processed exactly once,
  (b) a node is processed only after all its dependencies.

The combination solves the diamond problem structurally: in a diamond
``A -> B -> D`` and ``A -> C -> D``, node ``D`` appears in the affected set
once and is processed after both ``B`` and ``C``.

Reference implementation (Go):
``dckms-private/private/it/ddd/grade/ascetic-ddd/observer/dag_change_manager-2.go``

Decision
--------

Adopt the DAGChangeManager pattern for the faker provider populate topology,
implemented as **a separate ProviderChangeManager (Mediator)** -- Variant A.

Variant A: Separate Mediator (accepted)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A dedicated ``ProviderChangeManager`` owns the dependency graph and controls the
``populate()`` invocation order. Providers delegate population to the manager
rather than recursively calling ``populate()`` on their dependencies.

Conceptual mapping:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - DAGChangeManager concept
     - Faker provider analog
   * - Subject
     - ``AggregateProvider`` (data source)
   * - Observer
     - ``ReferenceProvider`` (depends on an ``AggregateProvider``)
   * - Subject + Observer (dual role)
     - ``AggregateProvider`` with ``ReferenceProvider`` fields (both source and consumer)
   * - ``deps[subject] -> []observer``
     - ``ReferenceProvider.aggregate_provider -> AggregateProvider``
   * - ``collectAffected()``
     - Collect all providers reachable from the root
   * - ``topoSort()``
     - Determine ``populate()`` invocation order
   * - Single notification per observer
     - Single ``populate()`` call per provider

Conceptual API::

    class ProviderChangeManager:
        """Mediator that owns the provider dependency graph
        and controls populate() invocation order."""

        deps:         dict[AggregateProvider, list[ReferenceProvider]]
        reverse_deps: dict[ReferenceProvider, list[AggregateProvider]]

        def register(self, agg_provider, ref_provider):
            """Called during provider network construction."""
            ...

        async def populate(self, root_provider, session):
            """Populate the entire reachable subgraph in topological order."""
            affected = set()
            self._collect_affected(root_provider, affected)
            sorted_providers = self._topo_sort(affected)
            for provider in sorted_providers:
                await provider.populate(session)  # exactly once, correct order

        def _collect_affected(self, provider, visited):
            """DFS: collect all reachable providers into a set."""
            for dep in self.deps.get(provider, []):
                if dep not in visited:
                    visited.add(dep)
                    if isinstance(dep, AggregateProvider):
                        self._collect_affected(dep, visited)

        def _topo_sort(self, affected):
            """Kahn's algorithm: topological order over the affected set."""
            in_degree = {p: 0 for p in affected}
            for p in affected:
                for dep in self.reverse_deps.get(p, []):
                    if dep in affected:
                        in_degree[p] += 1
            queue = [p for p, deg in in_degree.items() if deg == 0]
            sorted_ = []
            while queue:
                node = queue.pop(0)
                sorted_.append(node)
                for dep in self.deps.get(node, []):
                    if dep in affected:
                        in_degree[dep] -= 1
                        if in_degree[dep] == 0:
                            queue.append(dep)
            return sorted_

Variant B: Inline topological sort (rejected)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The topological sort logic would live inside the root ``AggregateProvider``,
which would introspect ``self.providers`` and
``ReferenceProvider.aggregate_provider`` to build the DAG on the fly.

Rejected because:

- Violates Single Responsibility: ``AggregateProvider`` would own both domain
  logic and graph traversal.
- No centralized graph: each ``populate()`` call would rebuild the DAG via
  introspection.
- Harder to extend for dynamic provider registration.
- Less aligned with GoF Mediator pattern, which explicitly separates the
  coordination concern into a dedicated object.

Key guarantees
^^^^^^^^^^^^^^^

1. **Each provider's populate() is called exactly once** -- deduplication via
   the visited set in ``collectAffected()``.

2. **Topological order** -- a provider is populated only after all its
   dependencies are populated. In the diamond ``Book -> Author -> Tenant`` and
   ``Book -> Publisher -> Tenant``, ``TenantProvider.populate()`` runs before
   both ``AuthorProvider.populate()`` and ``PublisherProvider.populate()``.

3. **All criteria arrive before populate** -- because the topological order
   processes dependencies first, all ``require()`` calls from all paths reach a
   shared provider **before** its ``populate()`` runs. Conflicts are detected
   before aggregate creation, not post-factum.

4. **Single point of control** -- the Mediator owns the graph and the traversal
   logic, making it easier to debug, trace, and extend (e.g., cycle detection,
   visualization, parallel population of independent branches).

Consequences
------------

- The ``ProviderChangeManager`` becomes the single entry point for population:
  client code calls ``await manager.populate(root_provider, session)`` instead
  of ``await root_provider.populate(session)`` directly.
- Provider ``populate()`` methods no longer call ``populate()`` on their
  dependencies -- the manager does this externally in the correct order.
- ADR-0004's ``require()`` validation remains as a safety net for edge cases,
  but the topological ordering makes ``DiamondUpdateConflict`` structurally
  impossible for well-formed DAGs.
- Registration of providers in the manager can be done either explicitly
  (``manager.register(agg, ref)``) or via introspection of provider annotations
  at setup time.
- The pattern aligns with GoF Mediator + Observer, making the design portable
  to Go (see ADR-0003) and recognizable to developers familiar with the
  original patterns.

Related
-------

- :doc:`0004-diamond-problem-in-provider-topology` -- predecessor ADR that
  introduced ``DiamondUpdateConflict`` validation
- GoF *Design Patterns*, p. 299-303 -- Mediator + Observer, ChangeManager,
  DAGChangeManager
- Reference implementation:
  ``dckms-private/private/it/ddd/grade/ascetic-ddd/observer/dag_change_manager-2.go``
