ADR-0006: MongoDB-like Query DSL for Faker Providers
=====================================================

.. index:: ADR; query DSL, MongoDB-like query, faker query, ReferenceProvider criteria, operator algebra

Status
------
Accepted

Context
-------

The faker module's provider hierarchy generates realistic test data by
composing providers: ``AggregateProvider`` creates aggregates,
``ReferenceProvider`` links them via foreign keys, ``ValueProvider`` produces
individual field values. Originally, providers communicated only concrete
values: ``require(27)`` meant "use exactly this ID".

This created several limitations.

Limitation 1: Only concrete values
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Providers could only accept exact values. There was no way to express
constraints like "a date after 2024-01-15" or "an age between 18 and 65".

In real data, business rule invariants create dependencies between fields
across aggregates. For example, a course session cannot start before the
course itself. A hire date must follow the company's founding date. An
invoice date cannot precede the contract date.

Without constraint-based selection, the only way to enforce such invariants was
imperative post-hoc correction -- generate a value, check the invariant, fix if
violated. This is fragile: the correction logic is scattered, hard to compose,
and does not participate in distribution.

Limitation 2: ReferenceProvider criteria limited to PK
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``ReferenceProvider.require()`` accepted only primary key values. To select a
related aggregate by its attributes (e.g., "an active company" or "a tenant
with a specific status"), there was no mechanism. The caller had to resolve
the criteria manually, find the ID, and pass it.

This was particularly problematic in diamond topologies (see :doc:`0004-diamond-problem-in-provider-topology`),
where constraints arrive from multiple paths and must be merged. A PK-only
interface cannot express "path 1 wants an active company, path 2 wants the
same company to be in the IT department". These are constraints on the
**aggregate**, not on its **ID**.

Limitation 3: Bidirectional data flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Without a unified criteria format, data flowed in both directions: providers
pulled values from dependencies and pushed values back via callbacks. This
bidirectional flow made the populate order fragile and hard to reason about.

The goal was a **unidirectional** flow: ``query -> input -> output``. A
provider receives criteria (query), resolves them to a concrete value (input),
and produces the output.

Decision
--------

Introduce a MongoDB-like query DSL (``ascetic_ddd.faker.domain.query``) as the
unified criteria language for all providers.

Why MongoDB-like syntax
^^^^^^^^^^^^^^^^^^^^^^^^

The key insight: MongoDB query syntax naturally separates the **operator with
its right operand** from the **left operand** (the field name)::

    {'$gt': 5}           # operator + right operand, no left operand
    {'$eq': 27}          # same: operator + value, field unknown
    {'age': {'$gt': 5}}  # left operand (field) + operator + right operand

This separation is ideal for the provider hierarchy. When a parent provider
calls ``child.require({'$gt': start_date})``, the child provider receives only
the operator and the value. The left operand -- which field this constraint
applies to -- is determined by the child's position in the provider tree, not
by the caller. The parent does not need to know the child's internal field
name.

In contrast, SQL-like syntax (``age > 5``) binds all three parts together,
requiring the caller to know the field name. This creates coupling between
providers that should be independent.

Operator tree
^^^^^^^^^^^^^^

Queries are parsed into an operator tree (AST):

- ``EqOperator(value)`` -- equality: ``{'$eq': 27}``
- ``ComparisonOperator(op, value)`` -- comparisons: ``{'$gt': 5}``,
  ``{'$lt': 10}``, ``{'$ne': 'deleted'}``, ``{'$gte': 0}``, ``{'$lte': 100}``
- ``InOperator(values)`` -- membership: ``{'$in': ['active', 'pending']}``
- ``IsNullOperator(value)`` -- null check: ``{'$is_null': True}`` or
  ``{'$is_null': False}``
- ``AndOperator(operands)`` -- implicit AND when multiple operators appear at
  the same level: ``{'$gt': 5, '$lt': 10}``
- ``OrOperator(operands)`` -- explicit OR: ``{'$or': [expr1, expr2]}``
- ``RelOperator(query)`` -- constraints on a related aggregate:
  ``{'$rel': {'status': {'$eq': 'active'}}}``
- ``CompositeQuery(fields)`` -- multi-field constraints:
  ``{'tenant_id': {'$eq': 15}, 'local_id': {'$eq': 27}}``

Scalar values are implicit ``$eq``::

    require(27)                  # -> EqOperator(27)
    require({'$eq': 27})         # -> EqOperator(27)  -- same

The ``$rel`` operator for ReferenceProvider
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``$rel`` operator carries constraints for a **related** aggregate, not for
the current one. ``ReferenceProvider`` automatically wraps non-``$rel`` criteria
into ``$rel`` with the aggregate's ID attribute::

    # PK constraint:
    ref_provider.require({'$eq': 27})
    # internally becomes: RelOperator(CompositeQuery({'id': EqOperator(27)}))

    # Aggregate attribute constraint:
    ref_provider.require({'$rel': {'is_active': {'$eq': True}}})
    # -> RelOperator(CompositeQuery({'is_active': EqOperator(True)}))

    # Both can be merged from different paths in a diamond:
    ref_provider.require({'$rel': {'is_active': {'$eq': True}}})
    ref_provider.require({'$eq': 27})
    # merged criteria: RelOperator(CompositeQuery({
    #     'is_active': EqOperator(True),
    #     'id': EqOperator(27)
    # }))

This enables diamond topologies where different paths contribute complementary
constraints on the same referenced aggregate.

Operator algebra and merging
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

All operators support ``__add__`` for merging criteria from multiple sources.
Same-type operators with equal values return self; conflicting values raise
``MergeConflict``; ``CompositeQuery.__add__`` recursively merges fields;
``RelOperator.__add__`` delegates to its inner ``CompositeQuery.__add__``.

This merging is essential for the diamond problem
(see :doc:`0004-diamond-problem-in-provider-topology`): multiple paths through
the provider graph contribute criteria to the same provider, and these criteria
must be composed, not overwritten.

The ``$is_null`` operator
^^^^^^^^^^^^^^^^^^^^^^^^^

``IsNullOperator(value: bool)`` checks whether a field is null (``True``) or
not null (``False``). Syntax: ``{'$is_null': True}`` / ``{'$is_null': False}``.

In evaluation, ``IsNullOperator(True)`` matches when state is ``None``;
``IsNullOperator(False)`` matches when state is not ``None``.

In PostgreSQL, compiles to ``IS NULL`` / ``IS NOT NULL`` (no parameters).

Rejected alternative: IsNullOperator with absorption
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

An ``IsNullOperator`` with "absorption" semantics (``IsNullOperator + RelOperator
= IsNullOperator``) was considered to replace ``ReferenceProvider``'s null FK
handling. Rejected because absorption is a **business rule of
ReferenceProvider** ("if FK is null, ignore aggregate constraints"), not a
property of operator algebra. Other providers might handle null differently
(raise an error, use a default). The null FK logic remains localized in
``ReferenceProvider``, where it is semantically justified.

The actual ``IsNullOperator`` uses standard merge semantics: same-type operators
with equal values return self; conflicting values (``True`` vs ``False``) raise
``MergeConflict``.

Visitor pattern
^^^^^^^^^^^^^^^^

Operations over the operator tree are implemented as visitors
(``IQueryVisitor``), keeping the operator classes stable when new operations
are added:

- ``QueryToDictVisitor`` -- serializes the tree back to dict format
- ``QueryToPlainValueVisitor`` -- extracts plain values for specifications
- ``EvaluateWalker`` / ``EvaluateVisitor`` -- evaluates criteria against state
  (used by ``AggregateProvider.require()`` to validate diamond constraints)
- ``PgQueryCompiler`` -- compiles to PostgreSQL SQL with ``@>`` (GIN index)
  optimization for ``$eq`` operators

The visitor pattern also satisfies Go portability (see :doc:`0003-go-portability`):
it maps to a simple interface + switch in Go, without reflection or
metaprogramming.

Consequences
------------

- **Unidirectional flow**: all providers accept criteria via ``require()`` as
  query operators. The flow is ``query -> input -> output``, with no callbacks
  or reverse propagation.

- **Business rule invariants in test data**: constraints like "date after X" or
  "value in range [A, B]" are expressed declaratively and participate in
  distribution. No post-hoc correction needed.

- **Rich ReferenceProvider criteria**: ``$rel`` allows selecting related
  aggregates by attributes, not just by PK. Combined with operator merging,
  this supports diamond topologies where multiple paths contribute
  complementary constraints.

- **Extensibility**: new operators (e.g., ``$regex``, ``$exists``) require
  adding a class, a visitor method, and handler implementations -- without
  modifying existing operators or visitors.

- **Dual evaluation**: the same operator tree is evaluated both in-memory
  (``EvaluateWalker`` for specification matching) and in PostgreSQL
  (``PgQueryCompiler`` for SQL generation), ensuring consistent semantics.

- **Go portability**: the operator tree, visitor interface, and parser use no
  Python-specific features (no metaclass magic, no decorators, no dynamic
  dispatch). The design maps directly to Go interfaces and switch statements.

Related
-------

- :doc:`0003-go-portability` -- design constraints for cross-language
  portability
- :doc:`0004-diamond-problem-in-provider-topology` -- diamond problem that
  motivated operator merging via ``__add__``
- :doc:`0005-dag-change-manager-for-provider-populate-topology` -- topological
  ordering ensures all ``require()`` calls arrive before ``populate()``
- ``ascetic_ddd/faker/domain/query/`` -- implementation
- ``ascetic_ddd/faker/infrastructure/query/pg_query_compiler.py`` -- PostgreSQL
  compilation
