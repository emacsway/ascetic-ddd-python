import typing
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass

__all__ = (
    "CausalDependency",
    "ICausalDependencyExporter",
)


@dataclass(frozen=True)
class CausalDependency:
    """
    This is enough to extract aggregate with required version from repository.
    And this is enough to check causal dependencies in Inbox.
    """
    tenant_id: typing.Any  # aggregate.id.tenant_id
    stream_id: typing.Any  # aggregate.id.internal_id
    stream_type: str  # bounded_context_name.aggregate_name
    stream_position: int  # aggregate.version

    def export(self, exporter: "ICausalDependencyExporter") -> None:
        exporter.set_tenant_id(self.tenant_id)
        exporter.set_stream_id(self.stream_id)
        exporter.set_stream_type(self.stream_type)
        exporter.set_stream_position(self.stream_position)


class ICausalDependencyExporter(metaclass=ABCMeta):

    @abstractmethod
    def set_tenant_id(self, value: typing.Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_stream_id(self, value: typing.Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_stream_type(self, value: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_stream_position(self, value: int) -> None:
        raise NotImplementedError
