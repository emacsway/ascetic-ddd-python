import typing

from ascetic_ddd.faker.domain.distributors.m2o import DummyDistributor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import ICursor, IM2ODistributor
from ascetic_ddd.faker.domain.providers._mixins import BaseCompositeDistributionProvider
from ascetic_ddd.faker.domain.query.visitors import dict_to_query
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.query_lookup_specification import QueryLookupSpecification
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
    _specification_factory: typing.Callable[..., ISpecification]

    def __init__(
            self,
            distributor: IM2ODistributor[CompositeInputT] | None = None,
            output_factory: typing.Callable[..., CompositeOutputT] | None = None,  # OutputT of each nested Provider.
            output_exporter: typing.Callable[[CompositeOutputT], CompositeInputT] | None = None,
            specification_factory: typing.Callable[..., ISpecification] = QueryLookupSpecification,
    ):
        if distributor is None:
            distributor = DummyDistributor()

        self._specification_factory = specification_factory
        super().__init__(
            distributor=distributor,
            output_factory=output_factory,
            output_exporter=output_exporter,
        )

    async def __create(self, session: ISession) -> CompositeOutputT:
        if self._output.is_nothing():
            raise RuntimeError("Provider '%s' has no output. Call populate() before create()." % self.provider_name)
        return typing.cast(CompositeOutputT, self._output.unwrap())

    async def create(self, session: ISession) -> CompositeOutputT:
        if self._output.is_nothing():
            if self.is_complete():
                self._set_output(await self._default_factory(session))
            else:
                if self._criteria is not None:
                    specification = self._specification_factory(self._criteria, self._output_exporter)
                else:
                    specification = EmptySpecification()

                try:
                    result = await self._distributor.next(session, specification)
                    if result.is_some():
                        output = result.unwrap()
                        input_ = self._output_exporter(output)
                        self._set_input(input_)
                        for attr, provider in self.providers.items():
                            await provider.populate(session)
                        self._set_output(output)
                    else:
                        self._set_output(None)
                except ICursor as cursor:
                    await self.do_populate(session)
                    for attr, provider in self.providers.items():
                        await provider.populate(session)
                    output = await self._default_factory(session, cursor.position)
                    self._set_output(output)
                    if not self.is_transient():
                        await cursor.append(session, self._output.unwrap())

        return typing.cast(CompositeOutputT, self._output.unwrap())

    async def populate(self, session: ISession) -> None:
        await self.create(session)

    async def do_populate(self, session: ISession) -> None:
        pass
