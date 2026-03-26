import typing

from ascetic_ddd.faker.domain.distributors.m2o import DummyDistributor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import ICursor, IM2ODistributor
from ascetic_ddd.faker.domain.providers._mixins import BaseCompositeDistributionProvider
from ascetic_ddd.session.interfaces import ISession

__all__ = (
    'CompositeValueProvider',
)


CompositeInputT = typing.TypeVar("CompositeInputT", bound=dict)
CompositeOutputT = typing.TypeVar("CompositeOutputT", bound=object)


class CompositeValueProvider(
    BaseCompositeDistributionProvider,
    typing.Generic[CompositeInputT, CompositeOutputT]
):
    """
    Immutable output - composite ValueObject.
    Architecture:
    ICompositeValueProvider = f(Σ input | None) = result,
    where
    result : T <- Distributor[T] <- (
        <- result : result ∈ Sᴛ ∧ P(specification) ~ 𝒟(S)  # select from a set with given probability distribution and Specification
        or
        <- result <- output_factory(Σ leaf_result)
            <- Σ IValueProvider(∈ Σ input) | ICompositeValueProvider(⊆ Σ input)
    ),
    where
        ":" means instance of type,
        "<-" means "from",
        "∈" means belongs,
        "Sᴛ" or "{x : T}" means set of type "T",
        "∧" means satisfies the condition P(),
        "~ 𝒟(S)" means according to the probability distribution,
        "Σx" means composition of "x",
        "⊆" means subset of a composition.
    """

    def __init__(
            self,
            distributor: IM2ODistributor[CompositeInputT] | None = None,
            output_factory: typing.Callable[..., CompositeOutputT] | None = None,  # OutputT of each nested Provider.
            output_exporter: typing.Callable[[CompositeOutputT], CompositeInputT] | None = None,
    ):
        if distributor is None:
            distributor = DummyDistributor()

        super().__init__(
            distributor=distributor,
            output_factory=output_factory,
            output_exporter=output_exporter,
        )

    async def populate(self, session: ISession) -> None:
        if self._output.is_nothing():
            if self.is_complete():
                await self._set_output(session, await self._default_factory(session))
            else:
                try:
                    result = await self._distributor.next(session, self._make_specification())
                    if result.is_some():
                        output = result.unwrap()
                        input_ = self.export(output)
                        self._set_input(input_)
                        for attr, provider in self.providers.items():
                            await provider.populate(session)
                        await self._set_output(session, output)
                    else:
                        await self._set_output(session, None)
                except ICursor as cursor:
                    await self.do_populate(session)
                    for attr, provider in self.providers.items():
                        await provider.populate(session)
                    output = await self._default_factory(session, cursor.position)
                    await self._set_output(session, output)
                    if not self.is_transient():
                        await cursor.append(session, self._output.unwrap())

    async def do_populate(self, session: ISession) -> None:
        pass
