import typing
from dataclasses import dataclass

__all__ = ("StreamId",)


@dataclass(frozen=True)
class StreamId:
    tenant_id: typing.Any
    stream_type: str
    stream_id: typing.Any
