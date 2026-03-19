import typing

from ascetic_ddd.faker.domain.sequencers.interfaces import ISequencer
from ascetic_ddd.faker.domain.sequencers.sequencer import Sequencer


__all__ = ('sequencer_factory',)


T = typing.TypeVar("T")


def sequencer_factory(
    name: str | None = None,
) -> ISequencer:
    """
    Factory for Sequencer.

    Args:
        name: Provider name for distributor (used for PG table naming).
    """
    sequencer = Sequencer()
    if name is not None:
        sequencer.provider_name = name
    return sequencer
