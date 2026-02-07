import copy
import functools
import typing
import abc
from collections.abc import Hashable, Callable

from ascetic_ddd.disposable import IDisposable
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.faker.domain.providers.interfaces import (
    IValueProvider, INameable, ICloningShunt, ICloneable,
    ICompositeValueProvider, IDependentProvider
)
from ascetic_ddd.faker.domain.query.operators import (
    IQueryOperator, CompositeQuery, MergeConflict
)
from ascetic_ddd.faker.domain.query.parser import parse_query
from ascetic_ddd.faker.domain.query.visitors import query_to_dict
from ascetic_ddd.faker.domain.providers.exceptions import DiamondUpdateConflict
from ascetic_ddd.seedwork.domain.session.interfaces import ISession
from ascetic_ddd.faker.domain.values.empty import empty, Empty
from ascetic_ddd.observable.interfaces import IObservable
from ascetic_ddd.observable.observable import Observable

__all__ = (
    'ObservableMixin',
    'NameableMixin',
    'CloneableMixin',
    'CloningShunt',
    'BaseProvider',
    'BaseDistributionProvider',
    'BaseCompositeProvider',
    'BaseCompositeDistributionProvider',
)

T_Input = typing.TypeVar("T_Input")
T_Output = typing.TypeVar("T_Output")
T_Cloneable = typing.TypeVar("T_Cloneable")


class ObservableMixin(Observable, IObservable, metaclass=abc.ABCMeta):

    _aspect_mapping = {
        "distributor": "_distributor"
    }

    def _split_aspect(self, aspect: typing.Hashable) -> tuple[str | None, typing.Hashable]:
        if isinstance(aspect, str) and "." in aspect:
            attr, inner_aspect = aspect.split('.', maxsplit=1)
            attr = self._aspect_mapping.get(attr, attr)
            return attr, inner_aspect
        return None, aspect

    def attach(self, aspect: Hashable, observer: Callable, id_: Hashable | None = None) -> IDisposable:
        attr, inner_aspect = self._split_aspect(aspect)
        if attr is not None:
            return getattr(self, attr).attach(inner_aspect, observer, id_)
        else:
            return super().attach(inner_aspect, observer, id_)

    def detach(self, aspect: Hashable, observer: Callable, id_: Hashable | None = None):
        attr, inner_aspect = self._split_aspect(aspect)
        if attr is not None:
            return getattr(self, attr).detach(inner_aspect, observer, id_)
        else:
            super().detach(inner_aspect, observer, id_)

    def notify(self, aspect: Hashable, *args, **kwargs):
        attr, inner_aspect = self._split_aspect(aspect)
        if attr is not None:
            return getattr(self, attr).notify(inner_aspect, *args, **kwargs)
        else:
            super().notify(inner_aspect, *args, **kwargs)

    async def anotify(self, aspect: Hashable, *args, **kwargs):
        attr, inner_aspect = self._split_aspect(aspect)
        if attr is not None:
            return await getattr(self, attr).anotify(inner_aspect, *args, **kwargs)
        else:
            await super().anotify(inner_aspect, *args, **kwargs)


class NameableMixin(INameable, metaclass=abc.ABCMeta):
    _provider_name: str | None = None

    @property
    def provider_name(self) -> str:
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


class CloneableMixin(ICloneable):

    def empty(self, shunt: ICloningShunt | None = None) -> typing.Self:
        if shunt is None:
            shunt = CloningShunt()
        if self in shunt:
            return shunt[self]
        c = copy.copy(self)
        self.do_empty(c, shunt)
        shunt[self] = c
        return c

    def do_empty(self, clone: typing.Self, shunt: ICloningShunt):
        pass


class BaseProvider(
    NameableMixin,
    ObservableMixin,
    CloneableMixin,
    IValueProvider[T_Input, T_Output],
    typing.Generic[T_Input, T_Output],
    metaclass=abc.ABCMeta
):
    _criteria: IQueryOperator | None = None
    _input: T_Input | Empty = empty
    _output: T_Output | Empty = empty

    def reset(self) -> None:
        self._criteria = None
        self._input = empty
        self._output = empty
        self.notify('criteria', self._criteria)
        self.notify('input', self._input)

    def require(self, criteria: dict[str, typing.Any]) -> None:
        """
        Set provider value using query format.

        Args:
            query: Query in format {'$eq': v} or scalar (implicit $eq)

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
            self._input = empty
            self._output = empty
            self.notify('criteria', self._criteria)

    def state(self) -> T_Input:
        """Return current query as dict format."""
        return self._input

    def do_empty(self, clone: typing.Self, shunt: ICloningShunt):
        clone._criteria = None
        clone._input = empty
        clone._output = empty

    def is_complete(self) -> bool:
        return self._output is not empty

    def is_transient(self) -> bool:
        return self._input is None

    def _set_input(self, input_: T_Input):
        self._input = input_
        self.notify('input', self._input)

    async def append(self, session: ISession, value: T_Output):
        pass

    async def setup(self, session: ISession):
        pass

    async def cleanup(self, session: ISession):
        pass


class BaseDistributionProvider(BaseProvider[T_Input, T_Output], typing.Generic[T_Input, T_Output],
                               metaclass=abc.ABCMeta):
    _distributor: IM2ODistributor[T_Output]

    def __init__(self, distributor: IM2ODistributor):
        self._distributor = distributor
        super().__init__()

    @property
    def provider_name(self) -> str:
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

    async def append(self, session: ISession, value: T_Input):
        await self._distributor.append(session, value)


class BaseCompositeProvider(
    ObservableMixin,
    CloneableMixin,
    ICompositeValueProvider[T_Input, T_Output],
    typing.Generic[T_Input, T_Output],
    metaclass=abc.ABCMeta
):

    _criteria: IQueryOperator | None = None
    _output: T_Output | Empty = empty
    _provider_name: str | None = None

    def is_complete(self) -> bool:
        return (
            self._output is not empty or
            all(provider.is_complete() for provider in self.providers.values())
        )

    def is_transient(self) -> bool:
        return any(provider.is_transient() for provider in self.providers.values())

    def do_empty(self, clone: typing.Self, shunt: ICloningShunt):
        clone._criteria = None
        clone._output = empty
        for attr, provider in self.providers.items():
            setattr(clone, attr, provider.empty(shunt))
        clone.on_init()

    def reset(self) -> None:
        self._criteria = None
        self._output = empty
        for provider in self.providers.values():
            provider.reset()
        self.notify('criteria', self._criteria)

    def require(self, criteria: dict[str, typing.Any]) -> None:
        """
        Set composite provider value using query format.

        Args:
            query: Query in format {'field': {'$eq': v}, ...}

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
            self._output = empty
            self._distribute_criteria(self._criteria)
            self.notify('criteria', self._criteria)

    def _distribute_criteria(self, query: IQueryOperator) -> None:
        """
        Distribute query to nested providers.

        Вложенная композиция поддерживается автоматически.
        """
        if isinstance(query, CompositeQuery):
            for attr, field_query in query.fields.items():
                provider = getattr(self, attr, None)
                if provider is None:
                    raise AttributeError(
                        f"Provider '{self.provider_name}': has no nested provider '{attr}'"
                    )
                provider.require(query_to_dict(field_query))

    def _set_input(self, input_: T_Input) -> None:
        """
        Unidirectional flow only. Don't call self.set()
        """
        for attr, val in input_.items():
            provider = getattr(self, attr, None)
            if provider is None:
                raise AttributeError(
                    f"Provider '{self.provider_name}': has no nested provider '{attr}'"
                )
            provider.require({'$eq': val})
        self.notify('input', input_)

    def state(self) -> T_Input:
        """Return current query as dict format, composed from nested providers."""
        value = dict()
        for attr, provider in self.providers.items():
            val = provider.state()
            if val is not empty:
                value[attr] = val
        return value

    async def append(self, session: ISession, value: T_Output):
        pass

    async def setup(self, session: ISession):
        for provider in self.providers.values():
            await provider.setup(session)
        for provider in self.dependent_providers.values():
            await provider.setup(session)

    async def cleanup(self, session: ISession):
        for provider in self.providers.values():
            await provider.cleanup(session)
        for provider in self.dependent_providers.values():
            await provider.cleanup(session)

    @classmethod
    @property
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
    @property
    @functools.cache
    def _dependent_provider_attrs(cls) -> list[str]:
        """Returns attribute names that are IDependentProvider."""
        attrs = list()
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
        return {i: getattr(self, i) for i in self._provider_attrs}

    @property
    def dependent_providers(self) -> dict[str, IDependentProvider[typing.Any, typing.Any, typing.Any]]:
        return {i: getattr(self, i) for i in self._dependent_provider_attrs}

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._provider_name = value
        for attr, provider in self.providers.items():
            provider.provider_name = "%s.%s" % (value, attr)
        for attr, provider in self.dependent_providers.items():
            provider.provider_name = "%s.%s" % (value, attr)


class BaseCompositeDistributionProvider(
    BaseCompositeProvider[T_Input, T_Output],
    typing.Generic[T_Input, T_Output],
    metaclass=abc.ABCMeta
):

    _criteria: IQueryOperator | None = None
    _output: T_Output | Empty = empty
    _provider_name: str | None = None
    _distributor: IM2ODistributor[T_Input]

    def __init__(self, distributor: IM2ODistributor[T_Input]):
        self._distributor = distributor
        super().__init__()

    async def append(self, session: ISession, value: T_Output):
        await self._distributor.append(session, value)
        await super().append(session, value)

    async def setup(self, session: ISession):
        await self._distributor.setup(session)
        await super().setup(session)

    async def cleanup(self, session: ISession):
        await self._distributor.cleanup(session)
        await super().cleanup(session)

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._provider_name = value
        self._distributor.provider_name = value
        for attr, provider in self.providers.items():
            provider.provider_name = "%s.%s" % (value, attr)
