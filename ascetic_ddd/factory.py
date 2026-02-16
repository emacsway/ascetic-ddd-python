from ascetic_ddd.event_bus import IEventBus, InMemoryEventBus
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.utils.amemo import amemo

__all__ = (
    "ascetic_ddd_factory",
    "BuildingBlocksFactory",
)


class BuildingBlocksFactory:
    @amemo
    async def make_in_memory_event_bus(self) -> IEventBus[ISession]:
        return InMemoryEventBus[ISession]()


ascetic_ddd_factory = BuildingBlocksFactory()
