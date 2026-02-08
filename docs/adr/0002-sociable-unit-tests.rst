ADR-0002: Sociable Unit Tests
=============================

.. index:: ADR; testing, sociable tests, unit tests

Status
------
Accepted

Context
-------
Unit tests can follow two strategies:

- **Solitary tests**: Each class is tested in isolation with all collaborators
  replaced by mocks/stubs.
- **Sociable tests**: Tests exercise a class together with its real
  collaborators, mocking only external dependencies.

Excessive mocking leads to brittle tests that break on refactoring even when
behavior is preserved. Mocks also hide integration issues that only surface in
production.

Decision
--------
Use sociable unit tests as the default testing strategy:

- Test with real collaborators whenever possible
- Use mocks only for external dependencies: database, network, filesystem
- Run tests with ``python -m unittest`` (never pytest)

.. code-block:: python

   import unittest

   class TestOrderService(unittest.TestCase):
       def test_create_order(self):
           # Real collaborators, no mocks
           repository = InMemoryOrderRepository()
           service = OrderService(repository)
           order = service.create_order(customer_id=1, items=['item1'])
           self.assertEqual(order.customer_id, 1)

Consequences
------------
- Tests exercise real interaction paths, catching integration issues early
- Refactoring internal collaborators does not break tests if behavior is
  preserved
- Test setup may be more involved (constructing real collaborator graphs)
- External dependencies still need mocks/stubs for determinism and speed
