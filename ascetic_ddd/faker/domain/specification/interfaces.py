import typing

from ascetic_ddd.session.interfaces import ISession


__all__ = (
    'ISpecificationVisitor',
    'ISpecificationVisitable',
    'ISpecification',
    'IResolvableSpecification',
)

T = typing.TypeVar("T", covariant=True)


class ISpecificationVisitor(typing.Protocol):

    def visit_query_specification(
            self,
            query: typing.Any,  # IQueryOperator
            aggregate_provider_accessor: typing.Callable[[], typing.Any] | None = None
    ):
        ...

    def visit_empty_specification(self):
        ...

    def visit_scope_specification(self, scope: typing.Hashable):
        ...


class ISpecificationVisitable(typing.Protocol[T]):

    def accept(self, visitor: ISpecificationVisitor):
        ...


class ISpecification(ISpecificationVisitable[T], typing.Protocol[T]):

    def __str__(self) -> str:
        ...

    def __hash__(self) -> int:
        ...

    def __eq__(self, other: object) -> bool:
        ...

    async def is_satisfied_by(self, session: ISession, obj: T) -> bool:
        ...


class IResolvableSpecification(ISpecification[T], typing.Protocol[T]):
    """Interface for a specification that requires pre-resolve."""

    async def resolve_nested(self, session: ISession) -> None:
        ...
