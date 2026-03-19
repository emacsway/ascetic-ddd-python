import typing

from ascetic_ddd.faker.domain.sequencers.interfaces import ISequencer
from ascetic_ddd.faker.infrastructure.sequencers.pg_sequencer import PgSequencer


__all__ = ('pg_sequencer_factory',)

T = typing.TypeVar("T")


def pg_sequencer_factory(
    name: str | None = None,
) -> ISequencer:
    """
    Factory for Sequencer.

    Args:
        name: Provider name for distributor (used for PG table naming).
    """
    sequencer = PgSequencer()
    if name is not None:
        sequencer.provider_name = name
    return sequencer
