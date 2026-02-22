import typing

from ascetic_ddd.seedwork.domain.aggregate.causal_dependency import ICausalDependencyExporter

__all__ = ("CausalDependencyExporter",)


class CausalDependencyExporter(ICausalDependencyExporter):
    data: dict[str, typing.Any]

    def __init__(self) -> None:
        self.data = {}

    def set_tenant_id(self, value: typing.Any) -> None:
        self.data["tenant_id"] = value

    def set_stream_id(self, value: typing.Any) -> None:
        self.data["aggregate_id"] = value

    def set_stream_type(self, value: str) -> None:
        self.data["aggregate_type"] = value

    def set_stream_position(self, value: int) -> None:
        self.data["aggregate_version"] = value
