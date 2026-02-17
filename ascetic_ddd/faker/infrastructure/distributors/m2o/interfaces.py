import typing


__all__ = ('IPgExternalSource',)


@typing.runtime_checkable
class IPgExternalSource(typing.Protocol):

    @property
    def table(self) -> str:
        ...
