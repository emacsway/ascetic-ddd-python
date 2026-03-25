import typing

from ascetic_ddd.session.interfaces import ISession


__all__ = (
    'ISpecificationVisitor',
    'ISpecificationVisitable',
    'ISpecification',
)

T = typing.TypeVar("T")
T_contra = typing.TypeVar("T_contra", contravariant=True)


class ISpecificationVisitor(typing.Protocol):

    def visit_query_specification(
            self,
            query: typing.Any,  # IQueryOperator
            aggregate_provider_accessor: typing.Callable[[], typing.Any] | None = None
    ):
        ...

    def visit_empty_specification(self):
        ...


class ISpecificationVisitable(typing.Protocol):

    def accept(self, visitor: ISpecificationVisitor):
        ...


class ISpecification(ISpecificationVisitable, typing.Protocol[T_contra]):

    def __str__(self) -> str:
        ...

    def __hash__(self) -> int:
        ...

    def __eq__(self, other: object) -> bool:
        ...

    async def is_satisfied_by(self, session: ISession, obj: T_contra) -> bool:
        ...
