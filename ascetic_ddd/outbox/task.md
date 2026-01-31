Мы только что реализовали ascetic_ddd/inbox

Теперь реализуем Transactional Outbox Pattern.

Изучи эту библиотеку /home/ivan/emacsway/apps/watermill-sql

Особое внимание удели файлам, которые заканчиваются на _postgresql.go

Изучи статью https://event-driven.io/en/rebuilding_read_models_skipping_events/ и рекурсивно все ссылки в тексте,
чтоб понять о проблемах Outbox Pattern.
В частности:
- https://event-driven.io/en/ordering_in_postgres_outbox/
- https://event-driven.io/en/rebuilding_event_driven_read_models/

Изучи статью https://www.kamilgrzybek.com/blog/posts/handling-domain-event-missing-part
Изучи статью https://www.kamilgrzybek.com/blog/posts/the-outbox-pattern

Сделай интерфейс IOutbox в файле ./interfaces.py с комментариями и схему БД в таблице ./init.sql

Обсудим, потом продолжим дальше.
