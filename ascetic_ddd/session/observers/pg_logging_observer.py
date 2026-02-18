import os
import logging

from ascetic_ddd.session.events import QueryEndedEvent

__all__ = ("PgLoggingObserver",)


class PgLoggingObserver:

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    async def __call__(self, event: QueryEndedEvent):
        self._logger.debug("pid: %s; time: %s, sql: %s; params: %r", os.getpid(), event.response_time, event.query, event.params)
