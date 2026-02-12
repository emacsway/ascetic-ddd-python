Доступ к состоянию агрегата без разрушения инкапсуляции
=======================================================

Status
------
Accepted

Context
-------

Хотя в Python инкапсуляция условна и основана на соглашении об именовании,
в проекте существует требование ":doc:`/adr/0003-go-portability`" о том,
что код должен быть легко портируем на другие языки программирования,
в частности на Golang.
Поэтому мы будем исходить из того, что доступ к защищенным атрибутам агрегата
извне отсутствует, и примеры будем рассматривать на Golang.

Инкапсуляция играет критически важную роль в управлении сложность.
Её назначение - гарантировать соблюдение инвариантов.

Как говорил Michael Feathers:

    💬️ "OO makes code understandable by encapsulating moving parts.
    FP makes code understandable by minimizing moving parts."
    -- `Michael Feathers <https://twitter.com/mfeathers/status/29581296216>`__

Возникает вопрос о том, как сохранить инкапсуляцию Агрегатов,
когда нам требуется его внутреннее состояние для формирования SQL-запроса,
или, наоборот, требуется установить состояние Агрегата из результата
выполнения SQL-запроса.

Существует несколько вариантов. Рассмотрим их подробнее.


Memento pattern
^^^^^^^^^^^^^^^

Memento оказался близко, но не по назначению. Суть Memento в том, что он не должен раскрывать свое состояние никому, кроме своего создателя:

    1. Preserving encapsulation boundaries. Memento avoids exposing information that only an originator should manage but that must be stored nevertheless outside the originator.
       The pattern shields other objects from potentially complex Originator internals, thereby preserving encapsulation boundaries.

    -- "Design Patterns: Elements of Reusable Object-Oriented Software" by Erich Gamma, Richard Helm, Ralph Johnson, John Vlissides

Тем не менее, этот подход используется некоторыми авторитетными источниками, например,
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

Интерфейс Scanner открывает дверь к изменяемости ValueObject, что противоречит основной его сути.
А так же открывает брешь в инкапсуляции Агрегата.
Справедливости ради, стоит отметить, что можно его реализовать таким образом,
чтобы он был только однократно мутируемым, предварительно удостоверившись в том,
что его значение не установлено.
Такой подход применяю часто для Identity Value Object for auto increment primary key.

Но есть еще один момент - метод ``Scan(src any) error`` вызывается у конкретного типа,
что препятствует использованию паттерна, известного как
`Special Case <https://martinfowler.com/eaaCatalog/specialCase.html>`__
или
`Null Object <https://refactoring.com/catalog/introduceSpecialCase.html>`__.

Кроме того, в некоторых случаях может потребоваться преобразовать
неизменяемые исторические данные для новой версии модели.
Вопрос затрагивался в разделе "4. Validating historical data" статьи
"`Always-Valid Domain Model <https://enterprisecraftsmanship.com/posts/always-valid-domain-model/>`__" by Vladimir Khorikov
и в разделе
"6. The use of ORMs within and outside of the always-valid boundary"
статьи
"`Database and Always-Valid Domain Model <https://enterprisecraftsmanship.com/posts/database-always-valid-domain-model/>`__" by Vladimir Khorikov.

С другой стороны, Valuer может возвращать только примитивные типы, а значит, он не пригоден для экспорта иерархической структуры состояния Агрегата:


    It is either nil, a type handled by a database driver's NamedValueChecker interface, or an instance of one of these types:

    - int64
    - float64
    - bool
    - []byte
    - string
    - time.Time

    -- `Источник <https://pkg.go.dev/database/sql/driver#Value>`__

В Python существуют аналогичные методы ``object.__getstate__()`` и ``object.__setstate__(state)``.


Reflection
^^^^^^^^^^

В документации `отсутствуют <https://pkg.go.dev/reflect#Value.FieldByName>`__ какие-либо упоминания об ограничении доступа к защищенным атрибутам структуры данных посредством рефлекции.

Но использование рефлексии в production mode для таких целей не выглядит привлекательным, в т.ч. и по соображениям производительности.
К тому же этот метод является, по сути, еще одним способом пробить брешь в инкапсуляции.

Похожий трюк используется
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

Такой вариант рассматривается в книге "`Implementing Domain-Driven Design <https://kalele.io/books/>`__" by Vaughn Vernon:

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

Ссылки по теме:

- "`More on getters and setters <https://www.infoworld.com/article/2072302/more-on-getters-and-setters.html>`__" by Allen Holub
- "`Save and load objects without breaking encapsulation <https://stackoverflow.com/questions/24921227/save-and-load-objects-without-breaking-encapsulation>`__" at Stackoverflow

Идею также можно посмотреть на примере:

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

Пример реализации на Golang:

.. literalinclude:: _media/0008-aggregate-encapsulation/exporter_1.go
   :language: go

Или на более лаконичном примере:

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

Замечательный вариант, но он использует интерфейсы,
и это получается несколько многословно - требуется декларировать сам тип (структуру), интерфейс, сеттеры.

В качестве альтернативы можно просто обязать Агрегат вернуть простую структуру,
и такие варианты так же встречаются в демонстрационных приложениях, например,
`here <https://github.com/kurrent-io/training-advanced-go/blob/52c0083aa717a7fac7c482c2b72e905b93c0a52a/domain/doctorday/day.go#L225>`__.

    💬️ "The goal of software architecture is to minimize the human resources required to build and maintain the required system."

    -- "Clean Architecture: A Craftsman's Guide to Software Structure and Design" by Robert C. Martin, перевод ООО Издательство "Питер"

:ref:`Второй <code-exporter-example-2>` из приведенных примеров содержит пакетированный сеттер, что делает его несколько менее многословным.

Однако, в таком случае, не получится обойти одним экземпляром экспортера
иерархию вложенных объектов агрегата из-за коллизии одноименного метода
``setDetails``,
например, при обходе агрегата и его композитного первичного ключа
(впрочем, в первом варианте коллизия тоже не исключена полностью).
Это могло бы быть удобным для составления списка параметров SQL-запроса.
Можно бы пожертвовать консистентностью именования, но это лишило бы второй вариант превосходства перед первым вариантом.
Также второй вариант обладает несколько большей хрупкостью при добавлении новых полей или их удалении.

Использование такого подхода в тестовых кейсах делает их несколько более многословными.

Можно было бы сказать, что тестировать нужно по принципам черного ящика, т.е. только внешнее поведение.
Совершенно верно, но только нам требуется не только внешнее поведение, но и достоверность сохранения введенной в конструктор Агрегата информации в БД.

    💬️ "It has long been known that testability is an attribute of good architectures.
    The Humble Object pattern is a good example, because the separation of
    the behaviors into testable and non-testable parts often defines
    an architectural boundary.
    The Presenter/View boundary is one of these boundaries,
    but there are many others."

    -- "Clean Architecture: A Craftsman's Guide to Software Structure and Design" by Robert C. Martin, перевод ООО Издательство "Питер"

Обратите внимание на то, что методы экспортера принимают ValueObject:

.. code-block::

  func (ex *EndorserExporter) SetId(val MemberId) {
      val.Export(func(v string) { ex.Id = v })
  }

Мы могли бы устранить эту избыточную осведомленность таким образом:

.. code-block::

  func (e Endorser) Export(ex EndorserExporterSetter) {
      e.id.Export(ex.SetId)
      ...
  }

  ...

  func (ex *EndorserExporter) SetId(val uint) {
      val.Export(func(v string) { ex.Id = v })
  }

Кажется, степень осведомленности сократилась.
Но есть и обратная сторона.
Предположим, ValueObject Id стал композитным.
Нам потребуется изменить не только интерфейс экспортера ValueObject, но и интерфейс экспортера самого агрегата.
У него появляется две причины для изменения.
Так же две причины для изменения появляется и в логике экспорта самого агрегата. Это нарушает принцип SRP.

.. admonition:: [UPDATE]

   На самом деле, не нужно, если метод будет возвращать экспортер для примитивных значений так же, как и для композитных значений:

   .. code-block::

      func (e Endorser) Export(ex EndorserExporterSetter) {
          e.id.Export(ex.SetId())
          ...
      }

      ...

      func (ex *EndorserExporter) SetId() func(uint) {
          return func(v string) { ex.Id = v }
      }

Вторая проблема заключается в том, что для автоинкрементных PK нам нужен доступ к методу Id.Scan(any).
И во втором варианте он не доступен, а значит, потребуется добавить публичный метод агрегата для доступа к нему.

Третья проблема - иногда нужно иметь доступ именно к ValueObject, например, при реализации Specification Pattern.

Четвертая проблема - сохранение консистентности между интерфейсами экспортера и импортера,
ведь, когда мы создаем агрегат, мы передаем в его конструктор ValueObjects, а не примитивные значения.
Этот вопрос имеет значение в языках, не имеющих пакетной области видимости, и агрегат должен предоставлять интерфейс импортера.
Что должен предоставлять импортер, примитивные типы или ValueObjects?

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
  Пятая проблема заключается в том, что становится многословней реализация экспортеров-запросов к БД для композитных ValueObject.
  Ведь нам нужно еще обработать полученные значения и вставить их в параметры запроса.
  Но метод уже вернул экспортер композитного ValueObject, а yield в Golang не поддерживается.
  Получив аргументом ValueObject мы можем делать с ним все, что угодно. Использовать стандартный экспортер для раскрытия состояния и вставлять его значения в параметры SQL-запроса.
  В другом варианте нам потребуется создавать структуру-бертку над экспортером, или возвращать анонимную структуру с функциями.



2. Returning structure
""""""""""""""""""""""

Возникает целесообразность облегчить метод экспортирования, придав ему сигнатуру
``Endorser.Export() EndorserState`` вместо ``Endorser.ExportTo(ex EndorserExporter)``.
В Python для этого есть даже задокументированные методы ``__getstate__()`` и ``__setstate__()``.
Получится что-то типа DTO с тем лишь отличием, что он пересекает не сетевые границы, а границы инкапсуляции Агрегата.

О таком же принципе этом писал Robert C. Martin:

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

    -- "Clean Architecture: A Craftsman's Guide to Software Structure and Design" by Robert C. Martin, перевод ООО Издательство "Питер"

Этот подход демонстрируется в
`Golang DDD ES/CQRS Reference Application <https://github.com/EventStore/training-advanced-go/blob/9cc2b5a4f3484dc643757c88480c4b6e371149fd/domain/doctorday/day.go#L225>`__
от контрибьюторов EventStore.

И такой же подход демонстрирует Nick Tune в
`sample code <https://github.com/elbandit/PPPDDD/blob/4d9d864fa6d9dfc0bad323ae21e949be1808b460/21%20-%20Repositories/DDDPPP.Chap21.EFExample/DDDPPP.Chap21.EFExample.Application/Model/Auction/Auction.cs#L48>`__
к своей книге.
Причем, применяет он его даже
`for Value Object <https://github.com/elbandit/PPPDDD/blob/4d9d864fa6d9dfc0bad323ae21e949be1808b460/21%20-%20Repositories/DDDPPP.Chap21.EFExample/DDDPPP.Chap21.EFExample.Application/Model/Auction/Money.cs#L58>`__.

.. literalinclude:: _media/0008-aggregate-encapsulation/exporter_2.go
   :language: go

Недостатком такого решения, который я успел обнаружить, является то,
что клиент не имеет возможности контролировать структуру экспортируемого объекта,
в отличии от варианта с интерфейсом.
Это затрудняет создание обобщенных классов, например,
`generic composite primary key <https://martinfowler.com/eaaCatalog/identityField.html>`__.
В результате плодятся промежуточные структуры, которые затем нужно преобразовывать к нужному виду.

Вместе с данными экспортируется и иерархия данных, т.е. внутренняя структура агрегата.
А значит, за обход структуры будет отвечать уже не агрегат в единственном месте,
а потребители экспортируемых данных во множественных местах, что удорожает изменение программы.

Затрудняется обратная совместимость, т.к. состояние единственно, а поведение множественно, что значит - версионируемо.

Знание о возвращаемом типе подталкивает к применению generics там, где это можно было бы избежать.

Возвращаемая структура и ее типизация является избыточным знанием, которое может препятствовать обобщению (абстрагированию) клиента этого метода, например, препятствовать выделению абстрактного класса паттерна Repository.
Вместо структуры гораздо удобней был бы массив/срез объектов с типом `driver.Value <https://pkg.go.dev/database/sql/driver#Value>`__.
Это еще один аргумент в пользу первого варианта с отдельными сеттерами для каждого атрибута Агрегата.


Импорт состояния
^^^^^^^^^^^^^^^^

В Golang область видимости структуры доступна всему пакету, поэтому нет большой необходимости реализовывать Importer/Provider - достаточно положить Reconstitutor в тот же пакет.

В других языках может потребоваться делать Importer/Provider, что образует брешь в инкапсуляции.
Поэтому импорт состояния делают либо посредством конструктора, если поддерживается множественная диспетчеризация (overloading), либо посредством статического метода класса - чтобы можно было создать, но невозможно было изменить.
Правда, при этом возникает сложность с синхронизацией состояния объектов в IdentityMap при фиксации изменений (commit), ведь состояние агрегата теперь недоступно для синхронизации.
В таком случае остается только очистить IdentityMap при фиксации изменений.


Export state of Immutable Types
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Агрегаты и сущности изменяемы, поэтому инкапсуляция гарантирует охрану инвариантов при изменении их состояния.
Но нужно ли делать экспортеры для неизменяемых типов, таких, как Value Object или Domain Event?

Nick Tune использует экспортер даже
`for Value Object <https://github.com/elbandit/PPPDDD/blob/4d9d864fa6d9dfc0bad323ae21e949be1808b460/21%20-%20Repositories/DDDPPP.Chap21.EFExample/DDDPPP.Chap21.EFExample.Application/Model/Auction/Money.cs#L58>`__.

Способ экспорта не должен зависеть от области видимости или доступности значения Value Object,
который может измениться с течением времени, как и сама структура Value Oject.
Иначе это внесет хрупкость в программу.

Композитные и простые ValueObject должны обрабатываться единообразно.

Greg Young об экспорте состояния Domain Events:

    💬 This table represents the actual Event Log.
    There will be one entry per event in this table.
    The event itself is stored in the [Data] column.
    The event is stored using some form of serialization, for the rest of
    this discussion the mechanism will assumed to be built in serialization
    although the use of the memento pattern can be highly advantageous.

    -- "`CQRS Documents by Greg Young <https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf>`__"


Decision
--------

Решение - использовать единообразный способ экспорта состояния агрегатов,
Value Objects and Domain Events посредством Accepting interface (Mediator).

Увеличение объема кода не является критичным в силу ":doc:`/adr/0007-scaffold`"

