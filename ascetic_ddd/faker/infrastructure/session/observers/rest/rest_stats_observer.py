
from ascetic_ddd.faker.domain.utils.stats import Collector
from ascetic_ddd.session.events import RequestEndedEvent

__all__ = ("RestStatsObserver",)


class RestStatsObserver:
    _stats: Collector

    def __init__(self, stats: Collector):
        self._stats = stats

    @property
    def stats(self) -> Collector:
        return self._stats

    async def request_ended(self, event: RequestEndedEvent):
        assert event.request_view.response_time is not None
        self.stats.append("%s.%s" % (event.request_view.label, str(event.request_view.status)), event.request_view.response_time)
