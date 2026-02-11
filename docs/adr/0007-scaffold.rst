ADR-0007: Code Generation over ORM
====================================

.. index:: ADR; scaffold, code generation, ORM, Raw SQL, CQRS, Shotgun Surgery

Status
------
Accepted

Context
-------

Although the project is ORM-agnostic, the primary focus is on using Raw SQL
without any ORM. There are several reasons for this.

- SQL syntax is far more stable than the interface of a typical ORM, which
  means that no ORM actually provides real abstraction -- the abstraction layer
  itself changes more frequently than the thing being abstracted. Too often
  ORMs die, release major backwards-incompatible versions, or get displaced by
  newer ORMs (making it harder to find developers willing to work with morally
  obsolete technologies).

- Switching databases requires more than just changing the dialect in an ORM --
  load testing, debugging, and optimization are still necessary. The apparent
  ease of swapping database engines is, in reality, illusory.

- The Repository Pattern primarily addresses dependency management (source code
  awareness). This means its interface should be owned by the application, not
  by a vendor. Using an ORM does not eliminate the need for dependency
  management.

- Only a few ORMs (and far from in every programming language) can boast good
  internal quality.

- ORMs often rely on reflection and metaprogramming, which negates the
  advantages of statically typed languages.

However, using Raw SQL introduces a classified Code Smell known as Shotgun
Surgery, since adding a single field to an Entity requires changes across many
files.

Martin Fowler himself, who popularized ORM with his book "Patterns of
Enterprise Application Architecture", wrote in the "Metadata Mapping" chapter
that there are two ways to solve this problem (and reduce Coupling):
"reflective program" and "code generation". He personally prefers the latter:

    Generated code is more explicit so you can see what's going on in the debugger;
    as a result I usually prefer generation to reflection,
    and I think it's usually easier for less sophisticated developers
    (which I guess makes me unsophisticated).

    -- "Patterns of Enterprise Application Architecture" by Martin Fowler,
    David Rice, Matthew Foemmel, Edward Hieatt, Robert Mee, Randy Stafford,
    chapter "Metadata Mapping".

In his article "`Orm Hate <https://martinfowler.com/bliki/OrmHate.html>`__" he
wrote that ORM solves a problem that does not exist in a CQRS application. In
other words, using CQRS can be seen as an alternative to using an ORM:

    ORMs are complex because they have to handle a bi-directional mapping.
    A uni-directional problem is much easier to work with, particularly if
    your needs aren't too complex and you are comfortable with SQL.
    This is one of the arguments for CQRS.

    -- "`Orm Hate <https://martinfowler.com/bliki/OrmHate.html>`__" by Martin Fowler

In the write-model, ORM becomes unnecessary -- putting an object into a
Repository and retrieving it are operations so simple that using an ORM would
be overengineering.

As for the read-model, there is a large number of off-the-shelf query filters
that accept requests in RQL, OData, JSONPath, or AIP-160 format and produce
ready-made SQL queries. Once again, there is no place for an ORM.

The project implements the Specification Pattern on an Expression Tree, with a
query parser in JSONPath format.

Decision
--------

Use code generation (scaffold) to eliminate Shotgun Surgery caused by Raw SQL
usage. A declarative YAML domain model produces a complete directory tree of
aggregate roots, value objects, domain events, and commands -- reducing the
number of files that must be manually edited when adding a new field.

See :doc:`/modules/scaffold/index` for the scaffold module documentation.

Consequences
------------

- **Reduced Shotgun Surgery**: adding a field to an aggregate requires editing
  only the YAML model and re-running the scaffold, instead of manually updating
  10-30 files.

- **Explicit generated code**: following Fowler's preference, the generated code
  is fully visible and debuggable -- no reflection or metaprogramming magic.

- **ORM-free architecture**: the combination of CQRS, Raw SQL, Repository
  Pattern, and code generation provides a clean alternative to ORM without
  sacrificing developer productivity.

Related
-------

- :doc:`/modules/scaffold/index` -- scaffold module documentation
- :doc:`0003-go-portability` -- design constraints for cross-language
  portability (scaffold generates code compatible with Go port)
