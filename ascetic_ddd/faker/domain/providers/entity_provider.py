import typing
from abc import ABCMeta

from ascetic_ddd.faker.domain.distributors.m2o.interfaces import ICursor
from ascetic_ddd.faker.domain.providers._mixins import BaseCompositeProvider
from ascetic_ddd.faker.domain.providers.interfaces import IEntityProvider
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.values.empty import empty

InputT = typing.TypeVar("InputT")
OutputT = typing.TypeVar("OutputT")


__all__ = ('EntityProvider',)


class EntityProvider(
    BaseCompositeProvider[InputT, OutputT],
    IEntityProvider[InputT, OutputT],
    typing.Generic[InputT, OutputT],
    metaclass=ABCMeta
):
    """
    Mutable output - composite Entity. Saved as part of aggregate.
    """
    _id_attr: str
    _output_exporter: typing.Callable[[OutputT], InputT] = None

    def __init__(
            self,
            output_factory: typing.Callable[[...], OutputT] | None = None,  # OutputT of each nested Provider.
            output_exporter: typing.Callable[[OutputT], InputT] | None = None,
    ):

        if self._output_exporter is None:
            if output_exporter is None:

                def output_exporter(value):
                    return value

            self._output_exporter = output_exporter

        super().__init__(output_factory=output_factory)

    async def create(self, session: ISession) -> OutputT:
        if self._output is empty:
            self._output = await self._default_factory(session)
        return self._output

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
