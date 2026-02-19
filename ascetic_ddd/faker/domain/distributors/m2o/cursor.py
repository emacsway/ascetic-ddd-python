import typing

from ascetic_ddd.faker.domain.distributors.m2o.interfaces import ICursor
from ascetic_ddd.session.interfaces import ISession

__all__ = ("Cursor",)

T = typing.TypeVar("T")


class Cursor(ICursor, typing.Generic[T]):
    """
    Interested decorators should catch the Cursor and create their own if they need to add an object to themselves.
    For example, if WeightedDistributor is used as a decorator for SequenceDistributor.
    """
    _position: int
    _callback: typing.Callable[[ISession, T, int], typing.Awaitable[None]]
    _delegate: ICursor | None = None

    def __init__(
            self,
            position: int,
            callback: typing.Callable[[ISession, T, int], typing.Awaitable[None]],
            delegate: ICursor | None = None
    ):
        self._position = position
        self._callback = callback
        self._delegate = delegate

    @property
    def position(self) -> int:
        if self._position >= 0:
            return self._position
        if self._delegate is not None:
            return self._delegate.position
        return -1

    async def append(self, session: ISession, value: T):
        await self._callback(session, value, self._position)
        if self._delegate is not None:
            await self._delegate.append(session, value)
