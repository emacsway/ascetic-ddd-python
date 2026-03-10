import typing

from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecificationVisitor, ISpecification

__all__ = ("EmptySpecification",)


T = typing.TypeVar("T")


class EmptySpecification(ISpecification[T], typing.Generic[T]):
    _hash = hash(frozenset())
    _str = str(frozenset())

    __slots__ = tuple()

    def __str__(self) -> str:
        return self._str

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EmptySpecification)

    async def is_satisfied_by(self, session: ISession, obj: T) -> bool:
        return True

    def accept(self, visitor: ISpecificationVisitor):
        visitor.visit_empty_specification()
