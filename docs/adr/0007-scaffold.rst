
Хотя проект является ORM-agnostic, основной упор сделан в нем на использование Raw-SQL без использования какого-либо ORM.
Этому есть несколько причин.

- Синтаксис SQL гораздо более стабильный, чем интерфейс среднестатистического ORM, а значит, никакого абстрагирования никакой ORM на самом деле не дает, ибо этот самый слой абстракции сам изменяется гораздо чаще, чем объект абстрагирования. Слишком часто ORMs умирают, выпускают мажорные обратно-несовместимые зависимости, или вытесняются с рынка новыми ORM (что затрудняет поиск специалистов, желающих работать с морально устаревшими технологиями).
- Для замены БД недостаточно просто переключить dialect в ORM - нужно провести еще и нагрузочное тестирование, отладку и оптимизацию. Кажущаяся простота замены типа БД, на самом деле, иллюзорна.
- Repository Pattern решает, в первую очередь, вопрос управления зависимостями (осведомленности по исходному коду). Это значит, его интерфейсом должно владеть приложение, а не вендор. Использование ORM не освобождает от управления зависимостями.
- Лишь немногие ORM (далеко не на всех языках программирования) способны похвастаться своим внутренним качеством.
- ORM зачастую используют рефлексию и метапрограммирование, что нивелирует превосходства использования статически-типизируемых языков.

Однако, используя Raw-SQL, мы обретаем классифицированный Code Smell, известный как Shotgun Surgery (Разлет Дроби), ибо добавление одного поля в Сущность требует правки многих файлов.

Сам Martin Fowler, прославивший ORM своей книгой "Patterns of Enterprise Application Architecture", писал в главе "Metadata Mapping" этой книги, что есть два способа решить эту проблему (и снизить Coupling): "reflective program" и "code generation", причем, сам он лично предпочитает второй вариант:

    Generated code is more explicit so you can see what's going on in the debugger;
    as a result I usually prefer generation to reflection,
    and I think it's usually easier for less sophisticated developers
    (which I guess makes me unsophisticated).

    -- "Patterns of Enterprise Application Architecture" by Martin Fowler, David Rice, Matthew Foemmel, Edward Hieatt, Robert Mee, Randy Stafford, chapter "Metadata Mapping".

А в своей статье `Orm Hate <https://martinfowler.com/bliki/OrmHate.html >`__ он писал, что ORM решает ту проблему, которая отсутствует в CQRS-приложении. Иными словами, использование CQRS можно рассматривать как альтернативу использованию ORM:

  ORMs are complex because they have to handle a bi-directional mapping. A uni-directional problem is much easier to work with, particularly if your needs aren't too complex and you are comfortable with SQL. This is one of the arguments for CQRS.

  -- `Orm Hate <https://martinfowler.com/bliki/OrmHate.html >`__ by Martin Fowler

В write-model ORM становится ненужным, т.е. положить объект в Repository и достать его из него - это операции настолько простые, что использование ORM будет overengineering.

Но что по поводу read-model? Существует большое количество коробочных фильтров запроса, которые принимают запрос в формате RQL, OData, JSONPath, AIP-160, и на выходе дают уже готовый SQL-запрос. Для ORM снова не нашлось места.

В проекте реализован Specification Pattern на Expression Tree, с парсером запроса в формате JSONPath.

