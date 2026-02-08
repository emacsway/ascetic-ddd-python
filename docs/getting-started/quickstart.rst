Quickstart
==========

.. index:: quickstart

This guide walks through the core concepts of ascetic-ddd with minimal examples.

Core Concepts
-------------

ascetic-ddd provides building blocks for Domain-Driven Design:

- :term:`Aggregate` roots with identity management
- :term:`Repository` pattern for persistence
- :term:`Specification` pattern for query criteria
- :term:`Saga` for distributed transactions
- :term:`Outbox` / :term:`Inbox` for reliable messaging

Defining an Aggregate
---------------------

.. code-block:: python

   from ascetic_ddd.seedwork.domain.aggregate import Aggregate

   class Order(Aggregate):
       def __init__(self, order_id, customer_id, items):
           self._order_id = order_id
           self._customer_id = customer_id
           self._items = items

Using Specifications
--------------------

Specifications allow you to express query criteria in a database-agnostic way:

.. code-block:: python

   from ascetic_ddd.specification.domain.lambda_filter.specification import LambdaFilterSpecification

   active_orders = LambdaFilterSpecification(
       lambda order: order['status'] == 'active'
   )

See the :doc:`/modules/index` section for detailed documentation of each module.
