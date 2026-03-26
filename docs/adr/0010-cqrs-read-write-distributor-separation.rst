ADR-0010: CQRS Read/Write Distributor Separation
=================================================

.. index:: ADR; CQRS distributor, distributor, WriteDistributor, shared store, Pipe, DistributedProvider

Status
------
Accepted

Context
-------

The faker module uses **distributors** to control value selection with
statistical distributions (weighted, Zipf/skew, uniform). A distributor
stores a pool of created values and selects from them according to a
distribution strategy.

Monolithic distributor
^^^^^^^^^^^^^^^^^^^^^^

In the initial design each distributor owned both the storage and the
selection strategy. This created a problem when the same pool of values
needed to be accessed with **different distribution strategies**.

The motivating scenario is ``Pipe`` with ``DistributedProvider``.

Pipe topology
^^^^^^^^^^^^^

``Pipe`` orchestrates sequential steps of aggregate generation. Each step
can be wrapped in a ``DistributedProvider`` that adds distributor-based
value selection::

    Pipe(
        PipeStep('first_model', DistributedProvider(
            first_model_faker,
            distributor=make_distributor(
                weights=[0.9, 0.5, 0.1, 0.01], mean=10),
        )),
        PipeStep('second_model', DistributedProvider(
            second_model_faker,
            distributor=make_distributor(
                weights=[0.3, 0.2], mean=20),
        ), require_fn=...),
    )

``DistributedProvider.populate()`` works as follows:

1. ``distributor.next()`` — tries to **read** an existing value from the pool
   using the configured distribution strategy.
2. If ``ICursor`` is raised (pool exhausted or probabilistic creation signal) —
   delegates to ``inner.populate()`` to **create** a new value, then
   ``cursor.append()`` **writes** it back to the pool.

The problem
^^^^^^^^^^^

Multiple ``DistributedProvider`` instances may target the same aggregate type
(e.g. ``FirstModel``) but with different distribution strategies:

- Pipe A selects FirstModels with ``weights=[0.9, 0.5]`` (heavy skew)
- Pipe B selects FirstModels with ``weights=[0.3, 0.2]`` (more uniform)

With a monolithic distributor each instance maintains its own pool. A
``FirstModel`` created via Pipe A's distributor is **invisible** to Pipe B's
distributor. This leads to:

- **Data duplication** — the same aggregate type stored in multiple pools.
- **Divergent pools** — each distributor sees only the values it created
  itself, distorting the intended distribution.
- **Wasted round-trips** — synchronizing pools requires explicit observer
  plumbing.

Decision
--------

Separate distributors into a **Write store** and **Read strategies** (CQRS
within the distributor):

- ``WriteDistributor`` / ``PgWriteDistributor`` — owns the data (indexes,
  PG table). Single point of mutation (``append``). Always raises ``ICursor``
  on ``next()`` to signal the caller to create a new value.
- ``WeightedDistributor`` / ``SkewDistributor`` / ``PgWeightedDistributor`` /
  ``PgSkewDistributor`` — **stateless read decorators** over a shared store.
  Each implements ``_distribute(n) -> int`` — a pure function that selects an
  index given pool size. All reads delegate to the store's data.
- ``NullableDistributor`` — decorator that probabilistically returns
  ``Nothing`` before delegating to the inner distributor.

The ``distributor_factory`` / ``pg_distributor_factory`` accept an optional
``store`` parameter to share a single write store across multiple read
strategies:

.. code-block:: python

   store = PgWriteDistributor()
   dist_a = pg_distributor_factory(weights=[0.9, 0.5], mean=5,  store=store)
   dist_b = pg_distributor_factory(weights=[0.3, 0.2], mean=20, store=store)
   # Both read from the same PG table with different strategies

When ``store`` is not provided, the factory creates one internally — the
single-distributor case works without any extra configuration.

Functional decomposition
^^^^^^^^^^^^^^^^^^^^^^^^

The separation mirrors the natural decomposition in functional languages:

============================  ====================================
OOP (Python)                  FP (Gleam / Elixir)
============================  ====================================
``WriteDistributor`` (state)  Actor / Process (holds mutable state)
``_distribute(n) -> int``     ``Strategy = fn(Int) -> Int`` (pure)
``NullableDistributor``       Higher-order function wrapper
``distributor_factory``       Config construction + process spawn
============================  ====================================

Consequences
------------

- Multiple ``DistributedProvider`` / ``ReferenceProvider`` instances for the
  same aggregate type can share a single pool via ``store`` parameter,
  eliminating data duplication and pool divergence.
- The distribution strategy (``_distribute``) is a pure function with no
  state, making it trivial to test and reason about in isolation.
- The factory API remains backwards-compatible: omitting ``store`` creates a
  dedicated store, preserving the simple single-distributor use case.
- Adding a new distribution strategy requires only a new class with
  ``_distribute(n) -> int`` — no changes to the store or the factory
  protocol.
- ``PgWriteDistributor`` handles the diamond problem for shared stores:
  ``setup()`` uses ``IF NOT EXISTS`` and an ``_initialized`` flag to ensure
  idempotent table creation even when multiple read distributors trigger
  setup concurrently.
