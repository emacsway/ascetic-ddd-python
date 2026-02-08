Glossary
========

.. glossary::
   :sorted:

   Aggregate
      A cluster of domain objects treated as a single unit for data changes.
      An aggregate has a root entity that controls all access to objects inside
      the boundary. External references are only allowed to the root.

   Entity
      A domain object defined by its identity rather than its attributes.
      Two entities with the same identity are considered the same object
      regardless of their current attribute values.

   Value Object
      A domain object defined entirely by its attributes, with no conceptual
      identity. Value objects are immutable and compared by value equality.

   Repository
      A collection-like interface for accessing aggregates. Repositories
      abstract the persistence mechanism, allowing domain logic to remain
      independent of storage details.

   Specification
      An object that encapsulates a boolean predicate over domain objects.
      Used to express query criteria, validation rules, or selection logic
      in a composable and reusable way.

   Saga
      A sequence of local transactions coordinated to implement a distributed
      business process. Each step has a compensating action that undoes its
      effect if a later step fails.

   Outbox
      A pattern where domain events are written to a database table (the outbox)
      within the same transaction as the business operation. A separate process
      reads the outbox and publishes events to the message broker.

   Inbox
      A pattern for idempotent message processing. Each incoming message ID
      is recorded; duplicate messages are detected and skipped.

   Provider
      In the faker module, a component responsible for generating or selecting
      a specific piece of test data. Providers form a directed acyclic graph
      where reference providers link aggregates.

   Distributor
      In the faker module, a strategy that controls how test data is selected
      from a pool or when new data must be created. Examples: sequence
      (round-robin), weighted (probability-based), random.

   Consumer Group
      A set of consumers that share the processing load for a stream of
      messages. Each message is delivered to exactly one consumer within
      the group.

   Session
      An implementation of the Unit of Work pattern. A session tracks changes
      to aggregates and commits them atomically to the database.

   Unit of Work
      A pattern that maintains a list of objects affected by a business
      transaction and coordinates the writing of changes and resolution
      of concurrency problems.

   Domain Event
      A record of something that happened in the domain. Domain events are
      used to communicate between aggregates and bounded contexts.

   Bounded Context
      A boundary within which a particular domain model applies. Different
      bounded contexts may have different models for the same real-world
      concept.
