import typing

from ascetic_ddd.session.interfaces import ISession

__all__ = ('IFactory',)

T_co = typing.TypeVar('T_co', covariant=True)


class IFactory(typing.Protocol[T_co]):
    """Stateless factory interface.

    Each call to create() produces a fresh value.
    No internal mutable state — no require/populate/output/reset cycle.
    Distributors and repositories hold state externally.
    """

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> T_co:
        ...

    async def setup(self, session: ISession) -> None:
        ...

    async def cleanup(self, session: ISession) -> None:
        ...
