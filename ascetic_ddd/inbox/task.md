# Inbox Pattern

В директории этого файла создай реализацию паттерна Inbox.

Цель этого паттерна - фиксировать входящие интеграционные сообщения, обеспечивать идемпотентность
и гарантировать Causal Consistency путем проверки Causal Dependencies.

Используется Raw SQL. Для коннекта к БД используется IPgSession.


## Алгоритм работы.


### Создание

При создании объекта принимаем зависимость ISessionPool и IMediator.


### Получение сообщения

Структура таблицы аналогична таблице ascetic_ddd/seedwork/infrastructure/repository/init.sql с тем лишь отличием,
что в ней будет еще и поля
- received_position unique not null biginteger auto increment from sequence
- processed_position nullable biginteger

При поступлении сообщения в метод receive(message) сохраняем его в таблицу БД.
Отдельно сохраняем колонки:

- tenant_id string
- stream_type string
- stream_id JsonB
- stream_position int
- event_type
- event_version
- payload JsonB
- metadata JsonB

Эти поля должны образовывать PK:
- tenant_id string
- stream_type string
- stream_id JsonB
- stream_position int


### Обработка сообщения

Метод handle() выбирает первое сообщение с processed_position IS NULL ORDER BY received_position DESC.

Проверяет что все его causal_dependencies уже обработаны (содержатся в таблице и имеют processed_position IS NOT NULL)
и вызывает абстрактный метод do_handle().
Если сообщение имеет необработанные зависимости, тогда выбираем следующее сообщение с
received_position > current_message_position AND processed_position IS NULL ORDER BY received_position DESC
и так до тех пор, пока в таблице остаются необработанные сообщения. Это можно сделать рекурсивным вызовом передав offset аргументом.



