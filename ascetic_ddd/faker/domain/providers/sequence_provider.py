import typing

from ascetic_ddd.faker.domain.providers._mixins import BaseProvider
from ascetic_ddd.faker.domain.providers.interfaces import IValueProvider
from ascetic_ddd.faker.domain.query.operators import EqOperator
from ascetic_ddd.faker.domain.generators.interfaces import IInputGenerator
from ascetic_ddd.faker.domain.generators.generators import prepare_input_generator
from ascetic_ddd.faker.domain.sequencers.interfaces import ISequencer
from ascetic_ddd.faker.domain.specification.query_lookup_specification import QueryLookupSpecification
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.scope_specification import ScopeSpecification
from ascetic_ddd.option import Nothing
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification


__all__ = ('SequenceProvider',)

InputT = typing.TypeVar("InputT")
OutputT = typing.TypeVar("OutputT")


class SequenceProvider(
    BaseProvider[InputT, OutputT],
    IValueProvider[InputT, OutputT],
    typing.Generic[InputT, OutputT]
):
    _sequencer: ISequencer
    _scope: typing.Hashable | None = None
    _input_generator: IInputGenerator[InputT] | None = None
    _output_factory: typing.Callable[[InputT | None], OutputT] = None  # type: ignore[assignment]  # OutputT of each nested Provider.
    _output_exporter: typing.Callable[[OutputT], InputT] = None  # type: ignore[assignment]

    def __init__(
            self,
            sequencer: ISequencer,
            input_generator: IInputGenerator[InputT] | None = None,
            output_factory: typing.Callable[[InputT], OutputT] | None = None,
            output_exporter: typing.Callable[[OutputT], InputT] | None = None,
    ):
        self._sequencer = sequencer

        if self._input_generator is None and input_generator is not None:
            self._input_generator = prepare_input_generator(input_generator)

        if self._output_factory is None:
            if output_factory is None:

                def output_factory(result):
                    return result

            self._output_factory = output_factory  # pyright: ignore[reportAttributeAccessIssue]

        if self._output_exporter is None:
            if output_exporter is None:

                def output_exporter(value):
                    return value

            self._output_exporter = output_exporter

        super().__init__()

    def require(self, criteria: dict[str, typing.Any]) -> None:
        if '$scope' in criteria:
            self._scope = criteria['$scope']
        self._output = Nothing()

    async def populate(self, session: ISession) -> None:
        if self._output.is_nothing():
            if isinstance(self._criteria, EqOperator):
                # Extract value from EqOperator
                self._set_input(self._criteria.value)
            if self._input.is_some():
                self._set_output(self._output_factory(typing.cast(InputT, self._input.unwrap())))
                # await cursor.append(session, self._output.unwrap())
            else:
                position = await self._sequencer.next(session, self._make_specification())
                assert self._input_generator is not None
                self._set_input(await self._input_generator(session, self._criteria, position))
                self._set_output(self._output_factory(typing.cast(InputT, self._input.unwrap())))

    def export(self, output: OutputT) -> InputT:
        return self._output_exporter(output)

    def _make_specification(self) -> ISpecification[OutputT]:
        if self._scope is not None:
            return ScopeSpecification[OutputT](self._scope)
        return EmptySpecification[OutputT]()

    @property
    def provider_name(self) -> str:
        assert self._provider_name is not None
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value: str):
        self._provider_name = value
        self._sequencer.provider_name = value

    async def setup(self, session: ISession):
        await self._sequencer.setup(session)
        await super().setup(session)

    async def cleanup(self, session: ISession):
        await self._sequencer.cleanup(session)
        await super().cleanup(session)
