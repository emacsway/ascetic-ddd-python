import typing

from ascetic_ddd.session.interfaces import ISession

__all__ = ('IProvider',)

T = typing.TypeVar('T')
T_co = typing.TypeVar('T_co', covariant=True)


class IProvider(typing.Protocol[T_co]):
    """Core provider interface for decorator-based composition.

    Each provider generates a value of type T. Providers compose via:
    - StructureProvider: named dict of child providers
    - Decorators: wrap IProvider adding one concern (modeling, persistence, distribution)
    """

    async def populate(self, session: ISession) -> None:
        ...

    def output(self) -> T_co:
        ...

    def require(self, criteria: dict[str, typing.Any]) -> None:
        ...

    def state(self) -> typing.Any:
        ...

    def reset(self, visited: set[int] | None = None) -> None:
        ...

    def is_complete(self) -> bool:
        ...

    def is_transient(self) -> bool:
        ...

    async def setup(self, session: ISession, visited: set[int] | None = None) -> None:
        ...

    async def cleanup(self, session: ISession, visited: set[int] | None = None) -> None:
        ...
