import typing
from abc import ABCMeta

from ascetic_ddd.faker.domain.distributors.m2o.interfaces import ICursor
from ascetic_ddd.faker.domain.providers._mixins import BaseCompositeProvider
from ascetic_ddd.faker.domain.providers.interfaces import IEntityProvider
from ascetic_ddd.session.interfaces import ISession
__all__ = ('EntityProvider',)

IdInputT = typing.TypeVar("IdInputT")
IdOutputT = typing.TypeVar("IdOutputT")
EntInputT = typing.TypeVar("EntInputT", bound=dict)
EntOutputT = typing.TypeVar("EntOutputT", bound=object)


class EntityProvider(
    BaseCompositeProvider[EntInputT, EntOutputT],
    IEntityProvider[EntInputT, EntOutputT, IdInputT, IdOutputT],
    typing.Generic[EntInputT, EntOutputT, IdInputT, IdOutputT],
    metaclass=ABCMeta
):
    """
    Mutable output - composite Entity. Saved as part of aggregate.
    """
    _id_attr: str
    _output_exporter: typing.Callable[[EntOutputT], EntInputT] = None

    def __init__(
            self,
            output_factory: typing.Callable[..., EntOutputT] | None = None,  # AggOutputT of each nested Provider.
            output_exporter: typing.Callable[[EntOutputT], EntInputT] | None = None,
    ):

        if self._output_exporter is None:
            if output_exporter is None:

                def output_exporter(value):
                    return value

            self._output_exporter = output_exporter

        super().__init__(output_factory=output_factory)

    async def create(self, session: ISession) -> EntOutputT:
        if not self._output_defined:
            self._set_output(await self._default_factory(session))
        return typing.cast(EntOutputT, self._output)

    @property
    def id_provider(self):
        return getattr(self, self._id_attr)

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return
        await self.do_populate(session)
        for attr, provider in self.providers.items():
            await provider.populate(session)

    async def do_populate(self, session: ISession) -> None:
        pass
