import typing
from typing import Callable

from hypothesis import strategies
from ascetic_ddd.faker.domain.query.operators import IQueryOperator
from ascetic_ddd.seedwork.domain.session.interfaces import ISession

__all__ = (
    'IInputGenerator',
    'IAnyInputGenerator'
)

T_Input = typing.TypeVar("T_Input")


class IInputGenerator(typing.Protocol[T_Input]):
    """
    Генератор значений.
    Принимает session, query (текущий запрос провайдера) и опциональный position (номер в последовательности).
    """

    async def __call__(self, session: ISession, query: IQueryOperator | None = None, position: int | None = None) -> T_Input:
        ...


IAnyInputGenerator: typing.TypeAlias = (
        IInputGenerator[T_Input] | typing.Iterable[T_Input] | strategies.SearchStrategy[T_Input] | Callable
)
