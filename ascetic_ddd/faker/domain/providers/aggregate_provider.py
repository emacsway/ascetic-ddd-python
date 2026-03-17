import typing
from abc import ABCMeta

from ascetic_ddd.faker.domain.providers._mixins import BaseCompositeProvider
from ascetic_ddd.faker.domain.providers.exceptions import DiamondUpdateConflict
from ascetic_ddd.faker.domain.query.evaluate_visitor import EvaluateWalker
from ascetic_ddd.faker.domain.query.operators import MergeConflict
from ascetic_ddd.faker.domain.query.parser import parse_query
from ascetic_ddd.faker.domain.query.visitors import dict_to_query, query_to_dict
from ascetic_ddd.faker.domain.providers.interfaces import (
    IAggregateProvider, IAggregateRepository,
)
from ascetic_ddd.session.interfaces import ISession
__all__ = ('AggregateProvider',)


IdInputT = typing.TypeVar("IdInputT")
IdOutputT = typing.TypeVar("IdOutputT")
AggInputT = typing.TypeVar("AggInputT", bound=dict)
AggOutputT = typing.TypeVar("AggOutputT", bound=object)


class AggregateProvider(
    BaseCompositeProvider[AggInputT, AggOutputT],
    IAggregateProvider[AggInputT, AggOutputT, IdInputT, IdOutputT],
    typing.Generic[AggInputT, AggOutputT, IdInputT, IdOutputT],
    metaclass=ABCMeta
):
    _id_attr: str
    _repository: IAggregateRepository[AggOutputT]

    def __init__(
            self,
            repository: IAggregateRepository,
            # distributor_factory: IM2ODistributorFactory,
            output_factory: typing.Callable[..., AggOutputT] | None = None,  # CompositeOutputT of each nested Provider.
            output_exporter: typing.Callable[[AggOutputT], AggInputT] | None = None,
            provider_name: str | None = None
    ):
        if self.provider_name is None:
            if provider_name is not None:
                self.provider_name = provider_name
            elif type(self).__name__ != AggregateProvider.__name__:
                self.provider_name = "%s.%s" % (type(self).__module__, type(self).__name__)
        self._repository = repository
        super().__init__(
            output_factory=output_factory,
            output_exporter=output_exporter,
        )

    def require(self, criteria: dict[str, typing.Any]) -> None:
        new_criteria = parse_query(criteria)
        if self._output.is_some():
            # Already created — validate state instead of resetting output
            state = self.state()
            walker = EvaluateWalker()
            if not walker.evaluate_sync(new_criteria, state):
                raise DiamondUpdateConflict(state, query_to_dict(new_criteria), self.provider_name)
            # State matches — merge criteria for bookkeeping
            if self._criteria is not None:
                try:
                    self._criteria = self._criteria + new_criteria
                except (TypeError, MergeConflict):
                    pass  # Validation already confirmed compatibility
            else:
                self._criteria = new_criteria
            # Don't distribute — nested providers already have their state
            return
        super().require(criteria)

    async def populate(self, session: ISession) -> None:
        # Prevent diamond problem (cycles in FK)
        # See also https://github.com/mikeboers/C3Linearize
        if self._output.is_nothing():

            await self.id_provider.populate(session)
            if self.id_provider.is_complete() and not self.id_provider.is_transient():
                # id_ may still be unknown here, since the aggregate has not been created yet.
                # But it may also be known, if its id_ came from a ReferenceProvider.
                # Skip repository lookup if id contains empty fields (auto-increment PKs)
                id_ = self.id_provider.output()
                output = await self._repository.get(session, id_)
                if output is not None:
                    input_ = self.export(output)
                    self._set_input(input_)
                    for attr, provider in self.providers.items():
                        await provider.populate(session)
                    self._set_output(output)
                    return

            await self.do_populate(session)
            for attr, provider in self.providers.items():
                await provider.populate(session)

            output = await self._default_factory(session)
            await self._repository.insert(session, output)
            state = self.export(output)
            id_value = state.get(self._id_attr)
            self.id_provider.require(dict_to_query(id_value))
            await self.id_provider.populate(session)
            # Auto-increment PK uses DummyDistributor which doesn't store values,
            # so append() is no-op. For composite PK with weighted distributor,
            # append() would add the new PK to the pool. Currently not needed
            # since PK providers don't use distribution-based distributors.
            # Note: ReferenceProvider observers listen to repository events
            # (via SubscriptionAggregateProviderAccessor), not to distributor.append().
            # await self.id_provider.append(session, getattr(result, self._id_attr))

            # self.require() could reset self._output
            self._set_output(output)

            # Create dependent entities AFTER this aggregate is created (they need its ID for FK)
            if self.dependent_providers:
                dependency_id = self.id_provider.state()
                for attr, dep_provider in self.dependent_providers.items():
                    dep_provider.set_dependency_id(dependency_id)
                    await dep_provider.populate(session)
                    dep_provider.create()

    async def do_populate(self, session: ISession) -> None:
        pass

    @property
    def id_provider(self):
        return getattr(self, self._id_attr)

    @property
    def repository(self) -> IAggregateRepository[AggOutputT]:
        return self._repository

    async def setup(self, session: ISession):
        await self._repository.setup(session)
        await super().setup(session)

    async def cleanup(self, session: ISession):
        await self._repository.cleanup(session)
        await super().cleanup(session)
