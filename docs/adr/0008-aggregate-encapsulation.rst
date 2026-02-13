ADR-0008: Accessing State of Encapsulated Aggregate
===================================================

.. index:: ADR; encapsulation, Aggregate, Exporter, Mediator, Value Object

Status
------
Accepted

Context
-------

Although in Python encapsulation is conventional and based on naming conventions,
the project has a requirement ":doc:`/adr/0003-go-portability`" that
code should be easily portable to other programming languages,
specifically to Golang.
Therefore, we will assume that external access to protected aggregate attributes
is absent, and examples will be considered in Golang.

Encapsulation plays a critically important role in managing complexity.
Its purpose is to guarantee invariant enforcement.

As Michael Feathers said:

    💬️ "OO makes code understandable by encapsulating moving parts.
    FP makes code understandable by minimizing moving parts."
    -- `Michael Feathers <https://twitter.com/mfeathers/status/29581296216>`__

The question arises of how to preserve Aggregate encapsulation
when we need its internal state to construct an SQL query,
or, conversely, need to set the Aggregate state from
an SQL query result.

There are several approaches. Let's examine them in detail.


Memento pattern
^^^^^^^^^^^^^^^

Memento turned out to be close, but not quite the right fit. The essence of Memento is that it must not reveal its state to anyone other than its originator:

    1. Preserving encapsulation boundaries. Memento avoids exposing information that only an originator should manage but that must be stored nevertheless outside the originator.
       The pattern shields other objects from potentially complex Originator internals, thereby preserving encapsulation boundaries.

    -- "Design Patterns: Elements of Reusable Object-Oriented Software" by Erich Gamma, Richard Helm, Ralph Johnson, John Vlissides

Nevertheless, this approach is used by some authoritative sources, for example,
`here <https://github.com/microsoftarchive/cqrs-journey/blob/6ffd9a8c8e865a9f8209552c52fa793fbd496d1f/source/Conference/Registration/SeatsAvailability.cs#L237>`__
and
`here <https://github.com/microsoftarchive/cqrs-journey/blob/6ffd9a8c8e865a9f8209552c52fa793fbd496d1f/source/Infrastructure/Azure/Infrastructure.Azure/EventSourcing/AzureEventSourcedRepository.cs#L31>`__.

    💬 The event is stored using some form of serialization, for the rest of this discussion the mechanism will assumed to be built in serialization although the use of the memento pattern can be highly advantageous.

    <...>

    Many use the default serialization package available with their platform with good results though the Memento pattern is quite useful when dealing with snapshots. The Memento pattern (or custom serialization) better insulates the domain over time as the structure of the domain objects change. The default serializer has versioning problems when the new structure is released (the existing snapshots must either deleted and recreated or updated to match the new schema). The use of the Memento pattern allows the separated versioning of the snapshot schema from the domain object itself.

    -- "`CQRS Documents by Greg Young <https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf>`__"


Valuer & Scanner
^^^^^^^^^^^^^^^^

- `Valuer <https://pkg.go.dev/database/sql/driver#Valuer>`__
- `Scanner <https://pkg.go.dev/database/sql#Scanner>`__

The Scanner interface opens the door to Value Object mutability, which contradicts its fundamental nature.
It also creates a breach in Aggregate encapsulation.
To be fair, it can be implemented in such a way
that it is only mutable once, by first verifying
that its value has not been set.
This approach is often used for Identity Value Object for auto-increment primary keys.

However, there is another issue - the ``Scan(src any) error`` method is called on a concrete type,
which prevents the use of the pattern known as
`Special Case <https://martinfowler.com/eaaCatalog/specialCase.html>`__
or
`Null Object <https://refactoring.com/catalog/introduceSpecialCase.html>`__.

Additionally, in some cases it may be necessary to transform
immutable historical data for a new model version.
This issue was addressed in section "4. Validating historical data" of the article
"`Always-Valid Domain Model <https://enterprisecraftsmanship.com/posts/always-valid-domain-model/>`__" by Vladimir Khorikov
and in section
"6. The use of ORMs within and outside of the always-valid boundary"
of the article
"`Database and Always-Valid Domain Model <https://enterprisecraftsmanship.com/posts/database-always-valid-domain-model/>`__" by Vladimir Khorikov.

On the other hand, Valuer can only return primitive types, which means it is not suitable for exporting the hierarchical structure of Aggregate state:


    It is either nil, a type handled by a database driver's NamedValueChecker interface, or an instance of one of these types:

    - int64
    - float64
    - bool
    - []byte
    - string
    - time.Time

    -- `Source <https://pkg.go.dev/database/sql/driver#Value>`__

Python has analogous methods ``object.__getstate__()`` and ``object.__setstate__(state)``.


Reflection
^^^^^^^^^^

The documentation `does not mention <https://pkg.go.dev/reflect#Value.FieldByName>`__ any restrictions on accessing protected data structure attributes via reflection.

However, using reflection in production for such purposes is not appealing, including for performance reasons.
Moreover, this method is essentially yet another way to breach encapsulation.

A similar trick is used
`here <https://stackoverflow.com/a/25405485>`__:

.. code-block:: go
   :caption: `How to marshal struct when some members are protected/inner/hidden <https://stackoverflow.com/a/25405485>`__

   package main

   import (
       "fmt"
       "reflect"

       "github.com/bitly/go-simplejson"
   )

   type A struct {
       name string `json:"name"`
       code string `json:"code"`
   }

   func marshal(a A) ([]byte, error) {
       j := simplejson.New()
       va := reflect.ValueOf(&a)
       vt := va.Elem()
       types := reflect.TypeOf(a)
       for i := 0; i < vt.NumField(); i++ {
           j.Set(types.Field(i).Tag.Get("json"), fmt.Sprintf("%v", reflect.Indirect(va).Field(i)))
       }
       return j.MarshalJSON()
   }

   func main() {
       a := A{name: "jessonchan", code: "abc"}
       b, _ := marshal(a)
       fmt.Println(string(b))
   }


Exporter
^^^^^^^^

1. Accepting interface (Mediator)
"""""""""""""""""""""""""""""""""

This approach is discussed in the book "`Implementing Domain-Driven Design <https://kalele.io/books/>`__" by Vaughn Vernon:

    Use a Mediator to Publish Aggregate Internal State

    To work around the problem of tight coupling between the model and
    its clients, you may choose to design Mediator [Gamma et al.]
    (aka Double-Dispatch and Callback) interfaces to which
    the Aggregate publishes its internal state.
    Clients would implement the Mediator interface, passing
    the implementer’s object reference to the Aggregate as a method argument.
    The Aggregate would then double-dispatch to that Mediator to publish
    the requested state, all without revealing its shape or structure.
    The trick is to not wed the Mediator’s interface to any sort of
    view specification, but to keep it focused on rendering
    Aggregate states of interest:

    .. code-block:: java

       public class BacklogItem ... {
           ...
           public void provideBacklogItemInterest(BacklogItemInterest anInterest) {
               anInterest.informTenantId(this.tenantId().id());
               anInterest.informProductId(this.productId().id());
               anInterest.informBacklogItemId(this.backlogItemId().id());
               anInterest.informStory(this.story());
               anInterest.informSummary(this.summary());
               anInterest.informType(this.type().toString());
           ...
           }
           public void provideTasksInterest(TasksInterest anInterest) {
               Set<Task> tasks = this.allTasks();
               anInterest.informTaskCount(tasks.size());
               for (Task task : tasks) {
               ...
               }
           }
           ...
       }

    The various interest providers may be implemented by other classes,
    much the same way that Entities (5) describe the way
    validation is delegated to separate validator classes.

    Be aware that some will consider this approach completely outside
    the responsibility of an Aggregate. Others will consider
    it a completely natural extension of a well-designed domain model.
    As always, such trade-offs must be discussed by your technical team members.

Related links:

- "`More on getters and setters <https://www.infoworld.com/article/2072302/more-on-getters-and-setters.html>`__" by Allen Holub
- "`Save and load objects without breaking encapsulation <https://stackoverflow.com/questions/24921227/save-and-load-objects-without-breaking-encapsulation>`__" at Stackoverflow

The idea can also be seen in the following example:

.. code-block:: java
   :caption: `Example by Allen Holub <https://www.infoworld.com/article/2072302/more-on-getters-and-setters.html>`__
   :name: code-exporter-example-1

    import java.util.Locale;

    public class Employee
    {   private Name        name;
        private EmployeeId  id;
        private Money       salary;

        public interface Exporter
        {   void addName    ( String name   );
            void addID      ( String id     );
            void addSalary  ( String salary );
        }

        public interface Importer
        {   String provideName();
            String provideID();
            String provideSalary();
            void   open();
            void   close();
        }

        public Employee( Importer builder )
        {   builder.open();
            this.name   = new Name      ( builder.provideName()     );
            this.id     = new EmployeeId( builder.provideID()       );
            this.salary = new Money     ( builder.provideSalary(),
                                          new Locale("en", "US")    );
            builder.close();
        }

        public void export( Exporter builder )
        {   builder.addName  ( name.toString()   );
            builder.addID    ( id.toString()     );
            builder.addSalary( salary.toString() );
        }

        //...
    }

Implementation example in Golang:

.. literalinclude:: _media/0008-aggregate-encapsulation/exporter_1.go
   :language: go

Or in a more concise example:

.. code-block:: java
   :caption: `Example from Stackoverflow <https://stackoverflow.com/questions/24921227/save-and-load-objects-without-breaking-encapsulation>`__
   :name: code-exporter-example-2

    interface PersonImporter {

        public int getAge();

        public String getId();
    }

    interface PersonExporter {

        public void setDetails(String id, int age);

    }

    class Person {

        private int age;
        private String id;

        public Person(PersonImporter importer) {
            age = importer.getAge();
            id = importer.getId();
        }

        public void export(PersonExporter exporter) {
            exporter.setDetails(id, age);
        }

    }

An excellent approach, but it uses interfaces,
and this turns out to be somewhat verbose - it requires declaring the type (struct) itself, the interface, and setters.

As an alternative, one can simply require the Aggregate to return a plain structure,
and such approaches also appear in demo applications, for example,
`here <https://github.com/kurrent-io/training-advanced-go/blob/52c0083aa717a7fac7c482c2b72e905b93c0a52a/domain/doctorday/day.go#L225>`__.

    💬️ "The goal of software architecture is to minimize the human resources required to build and maintain the required system."

    -- "Clean Architecture: A Craftsman's Guide to Software Structure and Design" by Robert C. Martin

:ref:`The second <code-exporter-example-2>` of the examples above contains a batched setter, which makes it somewhat less verbose.

However, in this case, it is not possible to traverse the hierarchy of nested
Aggregate objects with a single exporter instance due to method name collision
with ``setDetails``,
for example, when traversing an Aggregate and its composite primary key
(though in the first approach, collisions are not entirely excluded either).
This could have been convenient for composing SQL query parameter lists.
One could sacrifice naming consistency, but that would strip the second approach of its advantage over the first.
The second approach is also somewhat more fragile when adding or removing fields.

Using this approach in test cases makes them somewhat more verbose.

One could argue that testing should follow black-box principles, i.e., only external behavior.
Absolutely true, but we need not only external behavior, but also verification that the information passed to the Aggregate constructor is correctly persisted in the database.

    💬️ "It has long been known that testability is an attribute of good architectures.
    The Humble Object pattern is a good example, because the separation of
    the behaviors into testable and non-testable parts often defines
    an architectural boundary.
    The Presenter/View boundary is one of these boundaries,
    but there are many others."

    -- "Clean Architecture: A Craftsman's Guide to Software Structure and Design" by Robert C. Martin

Note that the exporter methods accept Value Objects:

.. code-block::

  func (ex *EndorserExporter) SetId(val MemberId) {
      val.Export(func(v string) { ex.Id = v })
  }

We could eliminate this excessive awareness as follows:

.. code-block::

  func (e Endorser) Export(ex EndorserExporterSetter) {
      e.id.Export(ex.SetId)
      ...
  }

  ...

  func (ex *EndorserExporter) SetId(val uint) {
      val.Export(func(v string) { ex.Id = v })
  }

It seems the degree of awareness has decreased.
But there is a flip side.
Suppose the Value Object Id becomes composite.
We would need to change not only the Value Object exporter interface, but also the Aggregate exporter interface itself.
It now has two reasons to change.
Likewise, two reasons for change appear in the Aggregate's export logic itself. This violates the SRP.

.. admonition:: [UPDATE]

   Actually, this is not necessary if the method returns an exporter for primitive values the same way as for composite values:

   .. code-block::

      func (e Endorser) Export(ex EndorserExporterSetter) {
          e.id.Export(ex.SetId())
          ...
      }

      ...

      func (ex *EndorserExporter) SetId() func(uint) {
          return func(v string) { ex.Id = v }
      }

The second problem is that for auto-increment PKs we need access to the Id.Scan(any) method.
And in the second approach it is not available, meaning we would need to add a public Aggregate method to access it.

The third problem is that sometimes we need access to the Value Object itself, for example, when implementing the Specification Pattern.

The fourth problem is maintaining consistency between the exporter and importer interfaces,
since when we create an Aggregate, we pass Value Objects to its constructor, not primitive values.
This matters in languages that lack package-level visibility, where the Aggregate must provide an importer interface.
What should the importer provide, primitive types or Value Objects?

    A FACTORY used for **reconstitution is very similar to one used for creation, with two major differences**.

    1. An ENTITY FACTORY used for reconstitution **does not assign a new tracking ID**.
       To do so would lose the continuity with the object's previous incarnation.
       So identifying attributes must be part of the input parameters in a FACTORY reconstituting a stored object.

    2. A FACTORY reconstituting an object will handle violation of an invariant differently.
       During creation of a new object, a FACTORY should simply balk when
       an invariant isn't met, but a more flexible response may be
       necessary in reconstitution.
       If an object already exists somewhere in the system
       (such as in the database), this fact cannot be ignored.
       Yet we also can't ignore the rule violation.
       There has to be some strategy for repairing such inconsistencies,
       which can make reconstitution more challenging than the creation of new objects.

    Figures 6.16 and 6.17 (on the next page) show two kinds of reconstitution.
    Object-mapping technologies may provide some or all of these services in
    the case of database reconstitution, which is convenient.
    Whenever there is exposed complexity in reconstituting an object from
    another medium, the FACTORY is a good option.

    -- "Domain-Driven Design: Tackling Complexity in the Heart of Software" by Eric Evans, Chapter "Six. The Life Cycle of a Domain Object :: Factories"

..
  The fifth problem is that database query exporter implementation becomes more verbose for composite Value Objects.
  We still need to process the received values and insert them into query parameters.
  But the method has already returned an exporter for the composite Value Object, and yield is not supported in Golang.
  When receiving a Value Object as an argument, we can do anything with it. Use the standard exporter to reveal state and insert its values into SQL query parameters.
  In the other approach, we would need to create a wrapper struct over the exporter, or return an anonymous struct with functions.



2. Returning structure
""""""""""""""""""""""

It becomes practical to simplify the export method, giving it the signature
``Endorser.Export() EndorserState`` instead of ``Endorser.ExportTo(ex EndorserExporter)``.
Python even has documented methods ``__getstate__()`` and ``__setstate__()`` for this purpose.
The result is something like a DTO, with the only difference being that it crosses not network boundaries, but the Aggregate's encapsulation boundaries.

Robert C. Martin wrote about the same principle:

    💬️ "Presenters are a form of the Humble Object pattern, which helps us identify and protect architectural boundaries."

    💬️ "Typically the data that crosses the boundaries consists of **simple data structures**.
    You can use **basic structs or simple data transfer objects** if you like.
    Or the data can simply be arguments in function calls.
    Or you can pack it into a hashmap, or construct it into an object.
    The important thing is that isolated, **simple data structures** are passed across the boundaries.
    We don't want to cheat and pass Entity objects or database rows.
    We don't want the data structures to have any kind of dependency that violates the Dependency Rule.

    For example, many database frameworks return a convenient data format in response to a query.
    We might call this a "row structure."
    We don't want to pass that row structure inward across a boundary.
    Doing so would violate the Dependency Rule because it would force an inner circle to know something about an outer circle.

    Thus, when we pass data across a boundary, it is always in the form that is most convenient for the inner circle."

    💬️ "It also uses the DataAccessInterface to bring the data used by those Entities into memory from the Database.
    Upon completion, the UseCaseInteractor gathers data from the Entities and constructs the OutputData as another **plain old Java object**.
    The OutputData is then passed through the OutputBoundary interface to the Presenter."

    -- "Clean Architecture: A Craftsman's Guide to Software Structure and Design" by Robert C. Martin

This approach is demonstrated in the
`Golang DDD ES/CQRS Reference Application <https://github.com/EventStore/training-advanced-go/blob/9cc2b5a4f3484dc643757c88480c4b6e371149fd/domain/doctorday/day.go#L225>`__
by EventStore contributors.

Nick Tune demonstrates the same approach in the
`sample code <https://github.com/elbandit/PPPDDD/blob/4d9d864fa6d9dfc0bad323ae21e949be1808b460/21%20-%20Repositories/DDDPPP.Chap21.EFExample/DDDPPP.Chap21.EFExample.Application/Model/Auction/Auction.cs#L48>`__
for his book.
Moreover, he applies it even
`for Value Object <https://github.com/elbandit/PPPDDD/blob/4d9d864fa6d9dfc0bad323ae21e949be1808b460/21%20-%20Repositories/DDDPPP.Chap21.EFExample/DDDPPP.Chap21.EFExample.Application/Model/Auction/Money.cs#L58>`__.

.. literalinclude:: _media/0008-aggregate-encapsulation/exporter_2.go
   :language: go

A disadvantage of this solution that I have identified is that
the client has no ability to control the structure of the exported object,
unlike the interface-based approach.
This makes it difficult to create generic classes, such as a
`generic composite primary key <https://martinfowler.com/eaaCatalog/identityField.html>`__.
As a result, intermediate structures proliferate that then need to be converted to the required form.

Along with the data, the data hierarchy is also exported, i.e., the Aggregate's internal structure.
This means that traversing the structure is no longer the Aggregate's responsibility in a single place,
but rather the responsibility of exported data consumers in multiple places, increasing the cost of program changes.

Backward compatibility becomes more difficult, since the state is singular while behavior is multiple, meaning it is versionable.

Knowledge of the return type pushes toward using generics where it could be avoided.

The returned structure and its typing constitute excessive knowledge that can hinder generalization (abstraction) of this method's client, for example, preventing the extraction of an abstract Repository pattern class.
Instead of a structure, an array/slice of `driver.Value <https://pkg.go.dev/database/sql/driver#Value>`__ typed objects would be much more convenient.
This is yet another argument in favor of the first approach with separate setters for each Aggregate attribute.


State Import
^^^^^^^^^^^^

In Golang, struct visibility is accessible to the entire package, so there is no great need to implement Importer/Provider - it is sufficient to place the Reconstitutor in the same package.

In other languages, it may be necessary to create an Importer/Provider, which creates a breach in encapsulation.
Therefore, state import usually is implemented either via a constructor, if multiple dispatch (overloading) is supported, or via a static class method - so that creation is possible but modification is not.
However, this creates a difficulty with synchronizing object state in the IdentityMap during commit, since the Aggregate state is now inaccessible for synchronization.
In such a case, the only option is to clear the IdentityMap on commit.


Export state of Immutable Types
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Aggregates and Entities are mutable, so encapsulation guarantees invariant protection when their state changes.
But do we need exporters for immutable types, such as Value Objects or Domain Events?

Nick Tune uses an exporter even
`for Value Object <https://github.com/elbandit/PPPDDD/blob/4d9d864fa6d9dfc0bad323ae21e949be1808b460/21%20-%20Repositories/DDDPPP.Chap21.EFExample/DDDPPP.Chap21.EFExample.Application/Model/Auction/Money.cs#L58>`__.

The export method should not depend on the scope of visibility or accessibility of the Value Object's value,
which may change over time, as may the Value Object's structure itself.
Otherwise, this introduces fragility into the program.

Composite and simple Value Objects should be handled uniformly.

Greg Young on exporting Domain Event state:

    💬 This table represents the actual Event Log.
    There will be one entry per event in this table.
    The event itself is stored in the [Data] column.
    The event is stored using some form of serialization, for the rest of
    this discussion the mechanism will assumed to be built in serialization
    although the use of the memento pattern can be highly advantageous.

    -- "`CQRS Documents by Greg Young <https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf>`__"


Decision
--------

The decision is to use a uniform state export method for Aggregates,
Value Objects and Domain Events via the Accepting interface (Mediator).

The increase in code volume is not critical due to ":doc:`/adr/0007-scaffold`".

Consequences
------------

- **Preserved encapsulation**: Aggregate internals are never directly exposed;
  all state access goes through explicit export/import interfaces.

- **Uniform export mechanism**: Aggregates, Value Objects and Domain Events all
  use the same Accepting interface (Mediator) pattern, reducing cognitive load.

- **Portability**: the approach works equally well in Golang (where package-level
  visibility helps) and in Python (where it enforces discipline beyond naming
  conventions). See :doc:`0003-go-portability`.

- **Scaffold-friendly**: the verbose boilerplate (exporter interfaces, setters)
  is generated automatically by the scaffold module. See :doc:`0007-scaffold`.

- **Testability**: exporter interfaces enable black-box verification of persisted
  state without accessing protected attributes.

- **Trade-off -- verbosity**: each Aggregate requires an exporter interface and
  corresponding setter methods, which adds code volume compared to direct
  attribute access or returning plain structures.

Related
-------

- :doc:`0003-go-portability` -- cross-language portability constraints
- :doc:`0007-scaffold` -- code generation to offset exporter boilerplate

