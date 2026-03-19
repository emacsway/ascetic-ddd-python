from ascetic_ddd.faker.domain.tests.sequencers.test_sequencer import SequencerTestCase
from ascetic_ddd.faker.infrastructure.sequencers.factory import pg_sequencer_factory


# logging.basicConfig(level="INFO")


class PgSequencerTestCase(SequencerTestCase):
    distributor_factory = staticmethod(pg_sequencer_factory)
