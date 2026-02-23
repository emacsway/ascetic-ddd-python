import typing
from typing import Callable

from hypothesis import strategies
from ascetic_ddd.faker.domain.query.operators import IQueryOperator
from ascetic_ddd.session.interfaces import ISession

__all__ = (
    'IInputGenerator',
    'IAnyInputGenerator'
)

InputT = typing.TypeVar("InputT")
InputT_co = typing.TypeVar("InputT_co", covariant=True)


class IInputGenerator(typing.Protocol[InputT_co]):
    """
    Value generator.
    Accepts session, query (the current provider query) and an optional position (sequence number).
    """

    async def __call__(self, session: ISession, query: IQueryOperator | None = None, position: int = -1) -> InputT_co:
        ...


IAnyInputGenerator: typing.TypeAlias = (
        IInputGenerator[InputT] | typing.Iterable[InputT] | strategies.SearchStrategy[InputT] | Callable
)
