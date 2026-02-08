ADR-0004: Diamond Problem in Provider Topology
================================================

.. index:: ADR; diamond problem, diamond problem, provider topology

Status
------
Accepted

Context
-------

The faker module's :term:`Provider` topology forms a directed acyclic graph (DAG)
where :term:`Aggregate` providers are connected via reference providers (foreign
keys). A **diamond problem** arises when the same ``AggregateProvider`` is
reachable from multiple paths.

Consider this topology::

   ThirdModelFaker
   +-- first_model_id  --> FirstModelFaker       (path 1)
   +-- second_model_id --> SecondModelFaker
   |                       +-- first_model_id --> FirstModelFaker  (path 2)
   +-- parent_id       --> ThirdModelFaker (self-reference, nullable)

``FirstModelFaker`` is reached from two paths. When ``ThirdModelFaker`` populates,
both paths call ``FirstModelFaker.require()`` with potentially different criteria,
but referring to the **same** aggregate instance.

Two sub-problems were identified:

1. **Conflicting** ``require()`` **calls on an already-created aggregate.**
   After ``FirstModelFaker`` has already created its output (via path 1), path 2
   calls ``require()`` again. The default ``BaseCompositeProvider.require()``
   resets ``_output`` to ``empty`` and redistributes criteria to nested providers,
   breaking the already-created state.

2. **Null FK propagation.** The nullable ``parent_id`` self-reference produces
   ``EqOperator(None)`` which gets wrapped into ``RelOperator`` and propagated
   through the distribution chain to a ``CompositeValueProvider`` (the composite
   PK provider), where ``EqOperator(None) + CompositeQuery(...)`` raises
   ``TypeError`` because ``EqOperator.__add__`` only accepts ``EqOperator``.

Decision
--------

**Fix 1: Validate instead of reset** (``AggregateProvider.require()``)

When ``AggregateProvider._output`` is already set (aggregate is created),
``require()`` validates the new criteria against the existing state using
``EvaluateWalker.evaluate_sync()`` instead of resetting and redistributing:

.. code-block:: python

   def require(self, criteria):
       new_criteria = parse_query(criteria)
       if self._output is not empty:
           # Already created - validate state instead of resetting
           state = self.state()
           walker = EvaluateWalker()
           if not walker.evaluate_sync(new_criteria, state):
               raise DiamondUpdateConflict(
                   state, query_to_dict(new_criteria), self.provider_name
               )
           # State matches - merge criteria for bookkeeping
           # Don't distribute - nested providers already have their state
           return
       super().require(criteria)

**Fix 2: Null FK early return** (``ReferenceProvider.require()``)

When a null FK (``EqOperator(None)``) is received, ``ReferenceProvider`` sets
``_input = None``, ``_output = None`` and returns immediately without wrapping
into ``RelOperator`` or propagating to the aggregate:

.. code-block:: python

   def require(self, criteria):
       new_criteria = parse_query(criteria)
       # Null FK - no reference. Don't propagate to aggregate.
       if isinstance(new_criteria, EqOperator) and new_criteria.value is None:
           self._input = None
           self._output = None
           return
       # ... normal flow

Consequences
------------

- Diamond topologies in provider graphs now work correctly: the first path
  creates the aggregate, and subsequent paths validate compatibility
- Null FK references are handled gracefully without propagation cascades
- ``EvaluateWalker`` provides sync evaluation without async overhead (each
  provider validates itself independently, no relation traversal needed)
- ``DiamondUpdateConflict`` is raised if a diamond produces genuinely
  incompatible constraints, catching topology bugs early
- The fix is backward-compatible: non-diamond topologies are unaffected

Related Files
-------------

- ``ascetic_ddd/faker/domain/providers/aggregate_provider.py`` —
  ``AggregateProvider.require()`` override
- ``ascetic_ddd/faker/domain/providers/reference_provider.py`` —
  ``ReferenceProvider.require()`` null FK handling
- ``ascetic_ddd/faker/domain/query/evaluate_visitor.py`` —
  ``EvaluateWalker.evaluate_sync()``
- ``ascetic_ddd/faker/domain/providers/exceptions.py`` —
  ``DiamondUpdateConflict``
