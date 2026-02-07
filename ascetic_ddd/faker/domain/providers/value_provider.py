import typing

from ascetic_ddd.faker.domain.distributors.m2o import DummyDistributor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import ICursor, IM2ODistributor
from ascetic_ddd.faker.domain.providers._mixins import BaseDistributionProvider
from ascetic_ddd.faker.domain.providers.interfaces import IValueProvider
from ascetic_ddd.faker.domain.query.operators import EqOperator
from ascetic_ddd.faker.domain.generators.interfaces import IInputGenerator
from ascetic_ddd.faker.domain.generators.generators import prepare_input_generator
from ascetic_ddd.faker.domain.specification import QueryResolvableSpecification
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.seedwork.domain.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.values.empty import empty

__all__ = ('ValueProvider',)

T_Input = typing.TypeVar("T_Input")
T_Output = typing.TypeVar("T_Output")


class ValueProvider(
    BaseDistributionProvider[T_Input, T_Output],
    IValueProvider[T_Input, T_Output],
    typing.Generic[T_Input, T_Output]
):
    """
    Immutable output - simple ValueObject.
    Architecture:
    IValueProvider = f(input | None) = result,
    where
    result : T <- Distributor[T] <- (
        <- result : result ∈ Sᴛ ∧ P(specification) ~ 𝒟(S)  # select from a set with given probability distribution and Specification
        or
        <- result <- output_factory(input)
            <- input <- (
                set(value)
                or
                ValueGenerator(position | None) <- position | None
            )
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
    _input_generator: IInputGenerator[T_Input] | None = None
    _output_factory: typing.Callable[[T_Input], T_Output] = None  # T_Output of each nested Provider.
    _output_exporter: typing.Callable[[T_Output], T_Input] = None
    _specification_factory: typing.Callable[..., ISpecification]

    def __init__(
            self,
            distributor: IM2ODistributor | None,
            input_generator: IInputGenerator[T_Input] | None = None,
            output_factory: typing.Callable[[T_Input], T_Output] | None = None,
            output_exporter: typing.Callable[[T_Output], T_Input] | None = None,
            specification_factory: typing.Callable[..., ISpecification] = QueryResolvableSpecification,
    ):
        if distributor is None:
            distributor = DummyDistributor()

        if self._input_generator is None and input_generator is not None:
            self._input_generator = prepare_input_generator(input_generator)

        if self._output_factory is None:
            if output_factory is None:

                def output_factory(result):
                    return result

            self._output_factory = output_factory

        if self._output_exporter is None:
            if output_exporter is None:

                def output_exporter(value):
                    return value

            self._output_exporter = output_exporter

        super().__init__(distributor=distributor)

    async def create(self, session: ISession) -> T_Output:
        if self._output is empty:
            raise RuntimeError("Provider '%s' has no output. Call populate() before create()." % self.provider_name)
        return self._output

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return

        if self._query is not None:
            # Extract value from EqOperator
            self._set_input(self._query.value if isinstance(self._query, EqOperator) else None)
        if self._input is not empty:
            self._output = self._output_factory(self._input)
            # await cursor.append(session, self._output)
            return

        if self._query is not None:
            specification = self._specification_factory(self._query)
        else:
            specification = EmptySpecification()
        specification = None  # FIXE: check how it works

        try:
            # EqOperator забьет индекс BaseDistributor, его нельзя сюда пускать.
            output = await self._distributor.next(session, specification)
            self._set_input(self._output_exporter(self._output))
            self._output = output
        except ICursor as cursor:
            if self._input_generator is None:
                self._set_input(None)
                self._output = self._output_factory(None)
            else:
                self._set_input(await self._input_generator(session, self._query, cursor.position))
                self._output = self._output_factory(self._input)
                await cursor.append(session, self._output)

    def _make_specification(self) -> ISpecification | None:
        return None
