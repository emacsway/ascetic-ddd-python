from urllib.parse import urlparse
try:
    from aiodogstatsd import Client
except ImportError:

    class Client:  # type: ignore[no-redef]
        pass

from ascetic_ddd.session.events import RequestEndedEvent, SessionScopeEndedEvent

__all__ = ("RestStatsdObserver", "make_statsd_client")


async def make_statsd_client(address="udp://127.0.0.1:8125", **kw):
    res = urlparse(address)
    client = Client(host=res.hostname, port=res.port, **kw)
    await client.connect()
    return client


class RestStatsdObserver:
    _client: Client

    def __init__(self, client: Client):
        self._client = client

    async def request_ended(self, event: RequestEndedEvent):
        """
        https://gr1n.github.io/aiodogstatsd/usage/
        """
        assert event.request_view.response_time is not None
        self._client.timing(event.request_view.label, value=event.request_view.response_time)
        self._client.increment(
            event.request_view.label + "." + str(event.request_view.status)
        )

    async def session_ended(self, event: SessionScopeEndedEvent):
        pass
        # client = self._client
        # await client.close()
