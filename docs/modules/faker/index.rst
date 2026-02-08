Faker
=====

.. index:: faker, test data generation

The faker module provides a framework for generating test data with realistic
relationships between :term:`Aggregate` instances.

Overview
--------

.. include:: ../../../ascetic_ddd/faker/README_RU.md
   :parser: myst_parser.sphinx_

Key Concepts
------------

.. index:: pair: faker; provider
.. index:: pair: faker; distributor

- **Provider**: A component that generates or selects a piece of test data.
  Providers form a directed acyclic graph.
- **Distributor**: Controls selection strategy (sequence, weighted, random).
- **Reference Provider**: Links aggregates via foreign key relationships.
- **Composite Value Provider**: Generates composite value objects.

API Reference
^^^^^^^^^^^^^

See the :doc:`/api/index` section for auto-generated API documentation of:

- :mod:`ascetic_ddd.faker.domain.providers.interfaces`
- :mod:`ascetic_ddd.faker.domain.distributors.m2o.interfaces`
- :mod:`ascetic_ddd.faker.domain.query.operators`
- :mod:`ascetic_ddd.faker.domain.specification.interfaces`
