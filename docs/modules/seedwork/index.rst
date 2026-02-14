Seedwork
========

.. index:: seedwork

The seedwork package provides foundational DDD abstractions that other modules
build upon.

Domain Layer
------------

.. index:: pair: seedwork; Aggregate
.. index:: pair: seedwork; Entity
.. index:: pair: seedwork; Value Object
.. index:: pair: seedwork; Identity

Core domain primitives:

- :term:`Aggregate` — consistency boundary with root entity
- :term:`Entity` — objects defined by identity
- :term:`Value Object` — immutable objects defined by attributes
- Identity — unique identification strategies

See the :doc:`/api/index` for auto-generated API documentation.

Infrastructure Layer
--------------------

.. index:: pair: seedwork; repository
.. index:: pair: seedwork; event store

PostgreSQL-based repository and event store implementations.

.. toctree::
   :maxdepth: 2

   infrastructure/index
