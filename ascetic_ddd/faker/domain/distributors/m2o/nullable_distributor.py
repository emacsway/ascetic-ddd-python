import random
import typing

from ascetic_ddd.option import Option, Nothing
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification

__all__ = ('NullableDistributor',)


T = typing.TypeVar("T")


class NullableDistributor(IM2ODistributor[T], typing.Generic[T]):
    _delegate: IM2ODistributor[T]
    _null_weight: float

    def __init__(
            self,
            delegate: IM2ODistributor[T],
            null_weight: float = 0
    ):
        self._delegate = delegate
        self._null_weight = null_weight

    async def next(
            self,
            session: ISession,
            specification: ISpecification[T],
    ) -> Option[T]:
        # if await specification.is_satisfied_by(session, None) and self._null_weight > 0 and self._is_null():
        if self._null_weight > 0 and self._is_null():
            return Nothing()
        return await self._delegate.next(session, specification)

    @property
    def provider_name(self):
        return self._delegate.provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._delegate.provider_name = value

    def _is_null(self) -> bool:
        return random.random() < self._null_weight

    async def append(self, session: ISession, value: T):
        await self._delegate.append(session, value)

    async def setup(self, session: ISession):
        await self._delegate.setup(session)

    async def cleanup(self, session: ISession):
        await self._delegate.cleanup(session)

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self
