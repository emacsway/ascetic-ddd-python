import copy
import functools
import typing
import abc
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.faker.domain.providers.interfaces import (
    IValueProvider,
    INameable,
    ICloningShunt,
    ILifecycleAble,
    ICompositeValueProvider,
    IDependentProvider,
)
from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, CompositeQuery, MergeConflict
)
from ascetic_ddd.faker.domain.query.parser import parse_query
from ascetic_ddd.faker.domain.query.visitors import query_to_dict
from ascetic_ddd.faker.domain.providers.exceptions import DiamondUpdateConflict
from ascetic_ddd.faker.domain.specification.empty_specification import EmptySpecification
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.query_lookup_specification import QueryLookupSpecification
from ascetic_ddd.option.option import Option, Some, Nothing
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.signals.interfaces import ISyncSignal, IAsyncSignal
from ascetic_ddd.signals.signal import SyncSignal, AsyncSignal
from ascetic_ddd.faker.domain.providers.events import CriteriaRequiredEvent, OutputPopulatedEvent

__all__ = (
    'NameableMixin',
    'LifecycleAbleMixin',
    'CloningShunt',
    'BaseProvider',
    'BaseDistributionProvider',
    'BaseCompositeProvider',
    'BaseCompositeDistributionProvider',
)

InputT = typing.TypeVar("InputT")
OutputT = typing.TypeVar("OutputT")
CompositeInputT = typing.TypeVar("CompositeInputT", bound=dict)
CompositeOutputT = typing.TypeVar("CompositeOutputT", bound=object)
CloneableT = typing.TypeVar("CloneableT")


class NameableMixin(INameable, metaclass=abc.ABCMeta):
    _provider_name: str | None = None

    @property
    def provider_name(self) -> str:
        assert self._provider_name is not None
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value: str):
        if self._provider_name is None:
            self._provider_name = value


class CloningShunt(ICloningShunt):

    def __init__(self):
        self._data = {}

    def __getitem__(self, key: typing.Hashable) -> typing.Any:
        return self._data[key]

    def __setitem__(self, key: typing.Hashable, value: typing.Any):
        self._data[key] = value

    def __contains__(self, key: typing.Hashable):
        return key in self._data


class LifecycleAbleMixin(ILifecycleAble):

    def __init__(self):
        super().__init__()
        self._do_init()

    def do_init(self):
        """User defined hook method."""
        pass

    def _do_init(self):
        """
        Library purpose template method.

        Do not force the user to call the super().do_init().
        """
        self.do_init()

    def reset(self, visited: set | None = None):
        if visited is None:
            visited = set()
        elif self in visited:
            return
        self._do_reset(visited)
        visited.add(self)

    def _do_reset(self, visited: set):
        self._do_init()

    def clone(self, shunt: ICloningShunt | None = None) -> typing.Self:
        if shunt is None:
            shunt = CloningShunt()
        if self in shunt:
            return shunt[self]
        c = copy.copy(self)
        self._do_clone(c, shunt)
        shunt[self] = c
        return c

    def _do_clone(self, clone: typing.Self, shunt: ICloningShunt):
        clone._do_init()


class BaseProvider(
    NameableMixin,
    LifecycleAbleMixin,
    IValueProvider[InputT, OutputT],
    typing.Generic[InputT, OutputT],
    metaclass=abc.ABCMeta
):
    _criteria: IQueryOperator | None = None
    _input: Option[InputT | None]
    _output: Option[OutputT | None]
    _is_transient: bool = False
    _on_required: ISyncSignal[CriteriaRequiredEvent]
    _on_populated: IAsyncSignal[OutputPopulatedEvent[OutputT]]

    def _do_init(self):
        self._criteria = None
        self._input = Nothing()
        self._output = Nothing()
        self._is_transient = False
        self._on_required = SyncSignal[CriteriaRequiredEvent]()
        self._on_populated = AsyncSignal[OutputPopulatedEvent[OutputT]]()
        super()._do_init()

    @property
    def on_required(self) -> ISyncSignal[CriteriaRequiredEvent]:
        return self._on_required

    @property
    def on_populated(self) -> IAsyncSignal[OutputPopulatedEvent[OutputT]]:
        return self._on_populated

    def require(self, criteria: dict[str, typing.Any]) -> None:
        """
        Set provider value using query format.

        Args:
            criteria: Query in format {'$eq': v} or scalar (implicit $eq)

        Examples:
            provider.require({'$eq': 5})
            provider.require(5)  # implicit $eq
        """
        new_criteria = parse_query(criteria)
        old_criteria = self._criteria
        if self._criteria is not None:
            try:
                self._criteria = self._criteria + new_criteria
            except MergeConflict as e:
                raise DiamondUpdateConflict(e.existing_value, e.new_value, self.provider_name) from e
        else:
            self._criteria = new_criteria
        # Only reset output if input actually changed
        if self._criteria != old_criteria:
            self._input = Nothing()
            self._output = Nothing()
            self._on_required.notify(CriteriaRequiredEvent(new_criteria))

    def output(self) -> OutputT:
        if self._output.is_nothing():
            raise RuntimeError("Provider '%s' has no output. Call populate() before output()." % self.provider_name)
        return typing.cast(OutputT, self._output.unwrap())

    def state(self) -> InputT:
        """Return current query as dict format."""
        assert self._input.is_some(), "Provider '%s' not populated" % self._provider_name
        return typing.cast(InputT, self._input.unwrap())

    def is_complete(self) -> bool:
        return self._output.is_some()

    def is_transient(self) -> bool:
        return self._is_transient

    def _set_input(self, input_: InputT | None):
        self._input = Some(input_)
        if input_ is not None:
            self._is_transient = False

    async def _set_output(self, session: ISession, output: OutputT | None, is_distributed: bool = False):
        self._output = Some(output)
        await self._on_populated.notify(
            OutputPopulatedEvent(session, typing.cast(OutputT, output), self.is_transient(), is_distributed)
        )

    async def append(self, session: ISession, value: OutputT):
        pass

    async def setup(self, session: ISession):
        pass

    async def cleanup(self, session: ISession):
        pass


class BaseDistributionProvider(BaseProvider[InputT, OutputT], typing.Generic[InputT, OutputT],
                               metaclass=abc.ABCMeta):
    _distributor: IM2ODistributor[OutputT]

    def __init__(self, distributor: IM2ODistributor[OutputT]):
        self._distributor = distributor
        super().__init__()

    @property
    def provider_name(self) -> str:
        assert self._provider_name is not None
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value: str):
        self._provider_name = value
        self._distributor.provider_name = value

    async def setup(self, session: ISession):
        await self._distributor.setup(session)
        await super().setup(session)

    async def cleanup(self, session: ISession):
        await self._distributor.cleanup(session)
        await super().cleanup(session)

    async def append(self, session: ISession, value: OutputT):
        await self._distributor.append(session, value)


class BaseCompositeProvider(
    LifecycleAbleMixin,
    ICompositeValueProvider[CompositeInputT, CompositeOutputT],
    typing.Generic[CompositeInputT, CompositeOutputT],
    metaclass=abc.ABCMeta
):

    _criteria: IQueryOperator | None = None
    _output: Option[CompositeOutputT | None]
    # CompositeOutputT of each nested Provider.
    _output_factory: typing.Callable[..., CompositeOutputT] = None  # type: ignore[assignment]
    _output_exporter: typing.Callable[[CompositeOutputT], CompositeInputT] = None  # type: ignore[assignment]
    _provider_name: str | None = None
    _on_required: ISyncSignal[CriteriaRequiredEvent]
    _on_populated: IAsyncSignal[OutputPopulatedEvent]

    def __init__(
            self,
            output_factory: typing.Callable[..., OutputT] | None = None,
            output_exporter: typing.Callable[[CompositeOutputT], CompositeInputT] | None = None,
    ):

        if self._output_factory is None:
            if output_factory is None:

                def output_factory(**kwargs):
                    return kwargs

            self._output_factory = output_factory  # pyright: ignore[reportAttributeAccessIssue]

        if self._output_exporter is None:
            if output_exporter is None:

                def output_exporter(value):
                    return value

            self._output_exporter = output_exporter

        super().__init__()

    def _do_init(self):
        self._criteria = None
        self._output = Nothing()
        self._on_required = SyncSignal[CriteriaRequiredEvent]()
        self._on_populated = AsyncSignal[OutputPopulatedEvent]()
        super()._do_init()

    @property
    def on_required(self) -> ISyncSignal[CriteriaRequiredEvent]:
        return self._on_required

    @property
    def on_populated(self) -> IAsyncSignal[OutputPopulatedEvent]:
        return self._on_populated

    def require(self, criteria: dict[str, typing.Any]) -> None:
        """
        Set composite provider value using query format.

        Args:
            criteria: Query in format {'field': {'$eq': v}, ...}

        Examples:
            provider.require({'tenant_id': {'$eq': 15}, 'local_id': {'$eq': 27}})
        """
        new_criteria = parse_query(criteria)
        old_criteria = self._criteria
        if self._criteria is not None:
            try:
                self._criteria = self._criteria + new_criteria
            except MergeConflict as e:
                raise DiamondUpdateConflict(e.existing_value, e.new_value, self.provider_name) from e
        else:
            self._criteria = new_criteria
        # Only reset output if input actually changed
        if self._criteria != old_criteria:
            self._output = Nothing()
            self._distribute_criteria(new_criteria)
            self._on_required.notify(CriteriaRequiredEvent(new_criteria))

    def _distribute_criteria(self, query: IQueryOperator) -> None:
        """
        Distribute query to nested providers.

        Nested composition is supported automatically.
        """
        if isinstance(query, CompositeQuery):
            for attr, field_query in query.fields.items():
                provider = getattr(self, attr, None)
                if provider is None:
                    raise AttributeError(
                        f"Provider '{self.provider_name}': has no nested provider '{attr}'"
                    )
                provider.require(query_to_dict(field_query))

    def _set_input(self, input_: CompositeInputT) -> None:
        """
        Unidirectional flow only. Don't call self.require()
        """
        for attr, val in input_.items():
            provider = getattr(self, attr, None)
            if provider is None:
                raise AttributeError(
                    f"Provider '{self.provider_name}': has no nested provider '{attr}'"
                )
            provider.require({'$eq': val})

    def output(self) -> CompositeOutputT:
        if self._output.is_nothing():
            raise RuntimeError("Provider '%s' has no output. Call populate() before output()." % self.provider_name)
        return typing.cast(CompositeOutputT, self._output.unwrap())

    def state(self) -> CompositeInputT:
        """Return current query as dict format, composed from nested providers."""
        value = dict()
        for attr, provider in self.providers.items():
            if provider.is_complete():
                value[attr] = provider.state()
        return typing.cast(CompositeInputT, value)

    def export(self, output: CompositeOutputT) -> CompositeInputT:
        return self._output_exporter(output)

    async def _default_factory(self, session: ISession, position: typing.Optional[int] = None):
        data = dict()
        for attr, provider in self.providers.items():
            data[attr] = provider.output()
        return self._output_factory(**data)

    async def _set_output(self, session: ISession, output: CompositeOutputT | None, is_distributed: bool = False):
        self._output = Some(output)
        await self._on_populated.notify(OutputPopulatedEvent(session, output, self.is_transient(), is_distributed))

    def is_complete(self) -> bool:
        return (
            self._output.is_some() or
            all(provider.is_complete() for provider in self.providers.values())
        )

    def is_transient(self) -> bool:
        return any(provider.is_transient() for provider in self.providers.values())

    def _do_reset(self, visited: set) -> None:
        for provider in self.providers.values():
            provider.reset(visited)
        # attach observers to dependencies now:
        super()._do_reset(visited)

    def _do_clone(self, clone: typing.Self, shunt: ICloningShunt):
        for attr, provider in self.providers.items():
            setattr(clone, attr, provider.clone(shunt))
        # attach observers to dependencies now:
        super()._do_clone(clone, shunt)

    async def append(self, session: ISession, value: CompositeOutputT):
        pass

    async def setup(self, session: ISession):
        for provider in self.providers.values():
            await provider.setup(session)
        for dep_provider in self.dependent_providers.values():
            await dep_provider.setup(session)

    async def cleanup(self, session: ISession):
        for provider in self.providers.values():
            await provider.cleanup(session)
        for dep_provider in self.dependent_providers.values():
            await dep_provider.cleanup(session)

    @classmethod
    @functools.cache
    def _provider_attrs(cls) -> list[str]:
        attrs = list()
        for cls_ in cls.mro():  # Use self.__dict__ or self.__reduce__() instead?
            if hasattr(cls_, '__annotations__'):
                for key, type_hint in cls_.__annotations__.items():
                    if not key.startswith('_') and key not in attrs:
                        # Skip IDependentProvider - it's handled separately
                        origin = typing.get_origin(type_hint) or type_hint
                        if isinstance(origin, type) and issubclass(origin, IDependentProvider):
                            continue
                        attrs.append(key)
        return attrs

    @classmethod
    @functools.cache
    def _dependent_provider_attrs(cls) -> list[str]:
        """Returns attribute names that are IDependentProvider."""
        attrs: list[str] = []
        for cls_ in cls.mro():
            if hasattr(cls_, '__annotations__'):
                for key, type_hint in cls_.__annotations__.items():
                    if not key.startswith('_') and key not in attrs:
                        origin = typing.get_origin(type_hint) or type_hint
                        if isinstance(origin, type) and issubclass(origin, IDependentProvider):
                            attrs.append(key)
        return attrs

    @property
    def providers(self) -> dict[str, IValueProvider[typing.Any, typing.Any]]:
        return {i: getattr(self, i) for i in self._provider_attrs()}

    @property
    def dependent_providers(self) -> dict[str, IDependentProvider[typing.Any, typing.Any, typing.Any, typing.Any]]:
        return {i: getattr(self, i) for i in self._dependent_provider_attrs()}

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._provider_name = value
        for attr, provider in self.providers.items():
            provider.provider_name = "%s.%s" % (value, attr)
        for attr, dep_provider in self.dependent_providers.items():
            dep_provider.provider_name = "%s.%s" % (value, attr)


class BaseCompositeDistributionProvider(
    BaseCompositeProvider[CompositeInputT, CompositeOutputT],
    typing.Generic[CompositeInputT, CompositeOutputT],
    metaclass=abc.ABCMeta
):
    _distributor: IM2ODistributor[CompositeOutputT]

    def __init__(
            self,
            distributor: IM2ODistributor[CompositeOutputT],
            output_factory: typing.Callable[..., CompositeOutputT] | None = None,
            output_exporter: typing.Callable[[CompositeOutputT], CompositeInputT] | None = None,
    ):
        self._distributor = distributor
        super().__init__(
            output_factory=output_factory,
            output_exporter=output_exporter
        )

    async def append(self, session: ISession, value: CompositeOutputT):
        await self._distributor.append(session, value)
        await super().append(session, value)

    def _make_specification(self) -> ISpecification[CompositeOutputT]:
        if self._criteria is not None:
            return QueryLookupSpecification[CompositeOutputT](
                self._criteria,
                self.export,
                aggregate_provider_accessor=lambda: self,
            )
        return EmptySpecification[CompositeOutputT]()

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._provider_name = value
        self._distributor.provider_name = value
        for attr, provider in self.providers.items():
            provider.provider_name = "%s.%s" % (value, attr)

    async def setup(self, session: ISession):
        await self._distributor.setup(session)
        await super().setup(session)

    async def cleanup(self, session: ISession):
        await self._distributor.cleanup(session)
        await super().cleanup(session)
