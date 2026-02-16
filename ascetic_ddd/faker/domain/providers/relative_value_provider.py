import typing

from ascetic_ddd.faker.domain.providers.interfaces import IRelativeValueProvider
from ascetic_ddd.faker.domain.providers.value_provider import ValueProvider
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.scope_specification import ScopeSpecification

__all__ = ('RelativeValueProvider',)

InputT = typing.TypeVar("InputT")
OutputT = typing.TypeVar("OutputT")


class RelativeValueProvider(
    ValueProvider[InputT, OutputT],
    IRelativeValueProvider[InputT, OutputT],
    typing.Generic[InputT, OutputT]
):
    _scope: typing.Hashable = frozenset()

    def set_scope(self, scope: typing.Hashable) -> None:
        self._scope = scope

    def reset(self) -> None:
        self._scope = frozenset()
        super().reset()

    def _make_specification(self) -> ISpecification | None:
        return ScopeSpecification(self._scope)
