import re
import json
import uuid
import typing
import pprint
import logging
import dataclasses
import datetime
import pstats

import requests

from collections import Counter
import cProfile as profile
from unittest import IsolatedAsyncioTestCase

from http.server import BaseHTTPRequestHandler

from ascetic_ddd.faker.domain.distributors.m2o.factory import distributor_factory
from ascetic_ddd.faker.domain.fp.providers.value_provider import ValueProvider
from ascetic_ddd.faker.domain.fp.providers.structure_provider import StructureProvider
from ascetic_ddd.faker.domain.fp.providers.modeled_provider import ModeledProvider
from ascetic_ddd.faker.domain.fp.providers.persisted_provider import PersistedProvider
from ascetic_ddd.faker.domain.fp.providers.distributed_provider import DistributedProvider
from ascetic_ddd.faker.domain.fp.providers.reference_provider import ReferenceProvider
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.infrastructure.distributors.m2o import pg_distributor_factory
from ascetic_ddd.session.rest_session import RestSessionPool
from ascetic_ddd.faker.infrastructure.tests.db import make_internal_pg_session_pool

from ascetic_ddd.faker.infrastructure.utils.json import JSONEncoder
from ascetic_ddd.faker.infrastructure.repositories import (
    InternalPgRepository, InMemoryRepository, RestRepository,
    CompositeAutoPkRepository as CompositeRepository
)
from ascetic_ddd.session.composite_session import CompositeSessionPool
from ascetic_ddd.faker.domain.utils.stats import Collector
from ascetic_ddd.session.events import SessionScopeStartedEvent, SessionScopeEndedEvent
from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.signals.signal import AsyncSignal
from ascetic_ddd.utils.tests.mock_server import get_free_port, start_mock_server

# logging.basicConfig(level="INFO")


# ################## Stub Session Pool for InMemory testing ##############################


class StubSession:
    """Simple stub session for in-memory testing."""

    def __init__(self, parent=None):
        self._parent = parent
        self._on_atomic_started = AsyncSignal[SessionScopeStartedEvent]()
        self._on_atomic_ended = AsyncSignal[SessionScopeEndedEvent]()

    @property
    def on_atomic_started(self) -> IAsyncSignal[SessionScopeStartedEvent]:
        return self._on_atomic_started

    @property
    def on_atomic_ended(self) -> IAsyncSignal[SessionScopeEndedEvent]:
        return self._on_atomic_ended

    def atomic(self):
        return StubTransactionContext(self)

    @property
    def response_time(self):
        return 0.0

    @property
    def stats(self):

        return Collector()


class StubTransactionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return StubSession(self._session)

    async def __aexit__(self, exc_type, exc, tb):
        pass


class StubSessionPool:
    """Simple stub session pool for in-memory testing."""

    def __init__(self):
        self._on_session_started = AsyncSignal[SessionScopeStartedEvent]()
        self._on_session_ended = AsyncSignal[SessionScopeEndedEvent]()

    @property
    def on_session_started(self) -> IAsyncSignal[SessionScopeStartedEvent]:
        return self._on_session_started

    @property
    def on_session_ended(self) -> IAsyncSignal[SessionScopeEndedEvent]:
        return self._on_session_ended

    def session(self):
        return StubSessionContext()

    @property
    def response_time(self):
        return 0.0

    @property
    def stats(self):

        return Collector()


class StubSessionContext:
    async def __aenter__(self):
        return StubSession()

    async def __aexit__(self, exc_type, exc, tb):
        pass


# ################## Models ##############################


FirstModelPk: typing.TypeAlias = uuid.UUID


@dataclasses.dataclass(kw_only=True)
class FirstModel:
    id: FirstModelPk
    attr2: str

    def __hash__(self):
        return hash(self.id)


SecondModelLocalPk: typing.TypeAlias = uuid.UUID


@dataclasses.dataclass(kw_only=True)
class SecondModelPk:
    id: SecondModelLocalPk
    first_model_id: FirstModelPk

    def __hash__(self):
        return hash((self.id, self.first_model_id))

    @property
    def value(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass(kw_only=True)
class SecondModel:
    id: SecondModelPk
    attr2: str

    def __hash__(self):
        return hash(self.id)


ThirdModelLocalPk: typing.TypeAlias = uuid.UUID


@dataclasses.dataclass(kw_only=True)
class ThirdModelPk:
    id: ThirdModelLocalPk
    first_model_id: FirstModelPk

    def __hash__(self):
        return hash((self.id, self.first_model_id))

    @property
    def value(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass(kw_only=True)
class ThirdModel:
    id: ThirdModelPk
    second_model_id: SecondModelPk
    attr2: str
    parent_id: ThirdModelPk

    def __hash__(self):
        return hash(self.id)


# ################## Repositories #############################


class FirstModelRepository(RestRepository[FirstModel]):
    _id_attr = 'id'
    _path = "first-model"


class SecondModelRepository(RestRepository[SecondModel]):
    _id_attr = 'id.id'
    _path = "second-model"


class ThirdModelRepository(RestRepository[ThirdModel]):
    _id_attr = 'id.id'
    _path = "third-model"


# ################## Export functions ##################################


def export_first_model(agg: FirstModel) -> dict:
    return {'id': agg.id, 'attr2': agg.attr2}


def export_second_model_pk(pk: SecondModelPk) -> dict:
    return {'id': pk.id, 'first_model_id': pk.first_model_id}


def export_second_model(agg: SecondModel) -> dict:
    if agg is None:
        return None
    return {
        'id': export_second_model_pk(agg.id),
        'attr2': agg.attr2,
    }


def export_third_model_pk(pk: ThirdModelPk) -> dict:
    return {'id': pk.id, 'first_model_id': pk.first_model_id}


def export_third_model(agg: ThirdModel) -> dict:
    return {
        'id': export_third_model_pk(agg.id),
        'second_model_id': export_second_model_pk(agg.second_model_id) if agg.second_model_id is not None else None,
        'attr2': agg.attr2,
        'parent_id': export_third_model_pk(agg.parent_id) if agg.parent_id is not None else None,
    }


# ################## Value Generators ##################################


class Attr2ValueGenerator:
    def __init__(self):
        self._count = 0

    async def __call__(self, session: ISession, position: int = -1):
        val = "attr2_%s" % self._count
        self._count += 1
        return val


# ################## Custom StructureProvider for ThirdModel ###########


class ThirdModelStructure(StructureProvider):
    """StructureProvider with tenant consistency enforcement.

    Populates PK first, then constrains second_model_id and parent_id
    to the same first_model_id (tenant isolation).
    """

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return
        # 1. Populate PK first
        pk_provider = self._providers['id']
        if not pk_provider.is_complete():
            await pk_provider.populate(session)
        pk = pk_provider.output()
        first_model_id = pk.first_model_id

        # 2. Constrain FKs to same tenant.
        # Match directly on composite PK fields stored in the distributor
        # (no $rel needed — the FK value itself contains first_model_id).
        self._providers['second_model_id'].require(
            {'first_model_id': {'$eq': first_model_id}}
        )
        self._providers['parent_id'].require(
            {'first_model_id': {'$eq': first_model_id}}
        )

        # 3. Populate remaining fields
        for name, provider in self._providers.items():
            if not provider.is_complete():
                await provider.populate(session)
        result = {
            name: provider.output()
            for name, provider in self._providers.items()
        }
        from ascetic_ddd.option import Some
        self._output = Some(result)
        self._is_transient = any(
            p.is_transient() for p in self._providers.values()
        )


# ################## Faker Factories ##################################


def make_first_model_faker(repository, make_distributor):
    """FP composition for FirstModel.

    Composition:
        PersistedProvider(
            ModeledProvider(
                StructureProvider(
                    id=ValueProvider(),
                    attr2=DistributedProvider(ValueProvider(gen), dist),
                ),
                factory=FirstModel, exporter=export_first_model,
            ),
            repository=repo, id_provider=id_prov,
        )
    """
    id_prov = ValueProvider()
    attr2_prov = DistributedProvider(
        ValueProvider(input_generator=Attr2ValueGenerator()),
        distributor=make_distributor(
            weights=[0.9, 0.5, 0.1, 0.01],
            mean=10,
        ),
    )
    structure = StructureProvider(id=id_prov, attr2=attr2_prov)
    modeled = ModeledProvider(
        structure,
        factory=FirstModel,
        exporter=export_first_model,
    )
    faker = PersistedProvider(
        modeled,
        repository=repository,
        id_provider=id_prov,
    )
    return faker


def make_second_model_faker(repository, first_model_faker, make_distributor):
    """FP composition for SecondModel with composite PK and FK to FirstModel.

    Composition:
        PersistedProvider(
            ModeledProvider(
                StructureProvider(
                    id=ModeledProvider(
                        DistributedProvider(
                            StructureProvider(
                                id=ValueProvider(),
                                first_model_id=DistributedProvider(
                                    ReferenceProvider(first_model_faker),
                                    dist,
                                ),
                            ),
                            dist,
                        ),
                        factory=SecondModelPk,
                    ),
                    attr2=DistributedProvider(ValueProvider(gen), dist),
                ),
                factory=SecondModel,
            ),
            repository=repo,
        )
    """
    # SecondModelPk providers
    pk_id_prov = ValueProvider()
    first_model_ref = DistributedProvider(
        ReferenceProvider(
            aggregate_provider=first_model_faker,
            id_attr='id',
        ),
        distributor=make_distributor(
            weights=[0.9, 0.5, 0.1, 0.01],
            mean=10,
        ),
    )
    pk_structure = StructureProvider(
        id=pk_id_prov,
        first_model_id=first_model_ref,
    )
    pk_distributed = DistributedProvider(
        pk_structure,
        distributor=make_distributor(),
    )
    pk_modeled = ModeledProvider(
        pk_distributed,
        factory=SecondModelPk,
        exporter=export_second_model_pk,
    )

    # SecondModel providers
    attr2_prov = DistributedProvider(
        ValueProvider(input_generator=Attr2ValueGenerator()),
        distributor=make_distributor(
            weights=[0.9, 0.5, 0.1, 0.01],
            mean=10,
        ),
    )
    structure = StructureProvider(id=pk_modeled, attr2=attr2_prov)
    modeled = ModeledProvider(
        structure,
        factory=SecondModel,
        exporter=export_second_model,
    )
    faker = PersistedProvider(
        modeled,
        repository=repository,
        id_provider=pk_modeled,
    )
    return faker


def make_third_model_faker(repository, first_model_faker, second_model_faker, make_distributor):
    """FP composition for ThirdModel with tenant-consistent FKs.

    Uses ThirdModelStructure to enforce tenant consistency:
    PK is populated first, then second_model_id and parent_id
    are constrained to the same first_model_id.
    """
    # ThirdModelPk providers
    pk_id_prov = ValueProvider()
    first_model_ref = DistributedProvider(
        ReferenceProvider(
            aggregate_provider=first_model_faker,
            id_attr='id',
        ),
        distributor=make_distributor(
            weights=[0.9, 0.5, 0.1, 0.01],
            mean=10,
        ),
    )
    pk_structure = StructureProvider(
        id=pk_id_prov,
        first_model_id=first_model_ref,
    )
    pk_distributed = DistributedProvider(
        pk_structure,
        distributor=make_distributor(),
    )
    pk_modeled = ModeledProvider(
        pk_distributed,
        factory=ThirdModelPk,
        exporter=export_third_model_pk,
    )

    # FK to SecondModel (nullable)
    second_model_ref = DistributedProvider(
        ReferenceProvider(
            aggregate_provider=second_model_faker,
            id_attr='id',
        ),
        distributor=make_distributor(
            weights=[0.9, 0.5, 0.1, 0.01],
            null_weight=0.5,
            mean=10,
        ),
        object_exporter=export_second_model_pk,
    )

    attr2_prov = DistributedProvider(
        ValueProvider(input_generator=Attr2ValueGenerator()),
        distributor=make_distributor(
            weights=[0.9, 0.5, 0.1, 0.01],
            mean=10,
        ),
    )

    # Self-reference for parent_id.
    # TODO: FP providers don't support clone() yet, so self-reference
    # creates infinite recursion. Using null_weight=1.0 to always produce None.
    # For full self-reference support, implement clone() or IPopulationShunt.
    parent_ref = DistributedProvider(
        ReferenceProvider(
            aggregate_provider=lambda: faker,
            id_attr='id',
        ),
        distributor=make_distributor(
            weights=[0.9, 0.5, 0.1, 0.01],
            null_weight=1.0,
            mean=10,
        ),
        object_exporter=export_third_model_pk,
    )

    # ThirdModel with tenant consistency
    structure = ThirdModelStructure(
        id=pk_modeled,
        second_model_id=second_model_ref,
        attr2=attr2_prov,
        parent_id=parent_ref,
    )
    modeled = ModeledProvider(
        structure,
        factory=ThirdModel,
        exporter=export_third_model,
    )
    faker = PersistedProvider(
        modeled,
        repository=repository,
        id_provider=pk_modeled,
    )
    return faker


# ################## Mock Server ################################################


class MockServerRequestHandler(BaseHTTPRequestHandler):
    URL_PATTERN = re.compile(r'/first-model')
    COMPOSITE_PK_URL_PATTERN = re.compile(r'/(second-model|third-model)')

    def do_POST(self):
        content_len = int(self.headers.get('Content-Length'))
        logging.debug(self.rfile.read(content_len))
        if re.search(self.URL_PATTERN, self.path):
            # Add response status code.
            self.send_response(requests.codes.ok)

            # Add response headers.
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()

            # Add response content.
            response_content = json.dumps({'id': uuid.uuid4()}, cls=JSONEncoder)
            self.wfile.write(response_content.encode('utf-8'))
            return
        elif re.search(self.COMPOSITE_PK_URL_PATTERN, self.path):
            # Add response status code.
            self.send_response(requests.codes.ok)

            # Add response headers.
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()

            # Add response content.
            response_content = json.dumps({'id': {'id': uuid.uuid4()}}, cls=JSONEncoder)
            self.wfile.write(response_content.encode('utf-8'))
            return


# ################## TestCases ###################################################


class FpRestPgIntegrationTestCase(IsolatedAsyncioTestCase):
    make_distributor = staticmethod(pg_distributor_factory)

    async def asyncSetUp(self):
        self.mock_server_port = get_free_port()
        self.mock_server = start_mock_server(self.mock_server_port, MockServerRequestHandler)
        self.session_pool = await self._make_session_pool()

    async def test_first_model_faker(self):
        faker = self._make_first_model_faker()
        async with self.session_pool.session() as session:
            async with session.atomic() as ts_session:
                await faker.setup(ts_session)
                await faker.populate(ts_session)
                agg = faker.output()
                self.assertIsInstance(agg.id, uuid.UUID)
                await faker.cleanup(ts_session)

    async def test_second_model_faker(self):
        faker = self._make_second_model_faker()
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await faker.setup(ts_session)
            await faker.populate(ts_session)
            agg = faker.output()
            self.assertIsInstance(agg.id.id, uuid.UUID)
            self.assertIsInstance(agg.id.first_model_id, uuid.UUID)
            await faker.cleanup(ts_session)

    async def test_third_model_faker(self):
        faker = self._make_third_model_faker()
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await faker.setup(ts_session)
            await faker.populate(ts_session)
            agg = faker.output()
            self.assertIsInstance(agg.id.id, uuid.UUID)
            self.assertIsInstance(agg.id.first_model_id, uuid.UUID)

            if agg.second_model_id is not None:
                self.assertIsInstance(agg.second_model_id.id, uuid.UUID)
                self.assertIsInstance(agg.second_model_id.first_model_id, uuid.UUID)

            # parent_id is always None (null_weight=1.0, clone not supported yet)
            self.assertIsNone(agg.parent_id)
            await faker.cleanup(ts_session)

    async def test_batch_third_model_faker(self):
        debug = False
        start_date = datetime.datetime.now()

        if debug:
            profiler = profile.Profile()
            profiler.enable()

        faker = self._make_third_model_faker()
        third_model_aggs = []
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await faker.setup(ts_session)
            for _ in range(1000):
                await faker.populate(ts_session)
                agg = faker.output()
                third_model_aggs.append(agg)
                self.assertIsInstance(agg.id.id, uuid.UUID)
                self.assertIsInstance(agg.id.first_model_id, uuid.UUID)

                if agg.second_model_id is not None:
                    self.assertIsInstance(agg.second_model_id.id, uuid.UUID)
                    self.assertIsInstance(agg.second_model_id.first_model_id, uuid.UUID)

                # parent_id is always None (null_weight=1.0)
                self.assertIsNone(agg.parent_id)

                faker.reset()

            await faker.cleanup(ts_session)

        if debug:
            profiler.disable()
            profiler.print_stats(sort='cumulative')

            # Below code is to add the stats to the file in human-readable format
            profiler.dump_stats('output.prof')
            stream = open('output.txt', 'w')
            stats = pstats.Stats('output.prof', stream=stream)
            stats.sort_stats('cumtime')
            stats.print_stats()

        run_time = datetime.datetime.now() - start_date
        logging.info("Run time: %s" % run_time)

        if debug:
            return

        logging.debug("ThirdModel.id.first_model_id:")
        counter = Counter([agg.id.first_model_id for agg in third_model_aggs])
        counter_repr = [(k, v) for k, v in sorted(counter.items(), key=lambda item: item[1], reverse=True)]
        logging.debug(pprint.pformat(counter_repr))

        logging.debug("ThirdModel.second_model_id:")
        counter = Counter([agg.second_model_id for agg in third_model_aggs])
        counter_repr = [(k, v) for k, v in sorted(counter.items(), key=lambda item: item[1], reverse=True)]
        logging.debug(pprint.pformat(counter_repr))

    async def _make_session_pool(self):
        rest_session_pool = RestSessionPool()
        pg_session_pool = await make_internal_pg_session_pool()
        session_pool = CompositeSessionPool(rest_session_pool, pg_session_pool)
        return session_pool

    def _make_first_model_faker(self):
        repository = self._make_first_model_repository()
        return make_first_model_faker(repository, self.make_distributor)

    def _make_second_model_faker(self, first_model_faker=None):
        if first_model_faker is None:
            first_model_faker = self._make_first_model_faker()
        repository = self._make_second_model_repository()
        return make_second_model_faker(
            repository,
            first_model_faker,
            self.make_distributor,
        )

    def _make_third_model_faker(self):
        first_model_faker = self._make_first_model_faker()
        repository = self._make_third_model_repository()
        return make_third_model_faker(
            repository,
            first_model_faker,
            self._make_second_model_faker(first_model_faker),
            self.make_distributor,
        )

    def _make_first_model_repository(self):
        external_repository = FirstModelRepository("http://localhost:%s" % self.mock_server_port)
        internal_repository = InternalPgRepository("first_model", export_first_model)
        return CompositeRepository[FirstModel](external_repository, internal_repository)

    def _make_second_model_repository(self):
        external_repository = SecondModelRepository("http://localhost:%s" % self.mock_server_port)
        internal_repository = InternalPgRepository("second_model", export_second_model)
        return CompositeRepository[SecondModel](external_repository, internal_repository)

    def _make_third_model_repository(self):
        external_repository = ThirdModelRepository("http://localhost:%s" % self.mock_server_port)
        internal_repository = InternalPgRepository("third_model", export_third_model)
        return CompositeRepository[ThirdModel](external_repository, internal_repository)

    async def asyncTearDown(self):
        await self.session_pool[1]._pool.close()


class FpRestMemoryIntegrationTestCase(FpRestPgIntegrationTestCase):
    make_distributor = staticmethod(distributor_factory)

    async def asyncTearDown(self):
        pass  # StubSessionPool doesn't need cleanup

    async def _make_session_pool(self):
        rest_session_pool = RestSessionPool()
        stub_session_pool = StubSessionPool()
        return CompositeSessionPool(rest_session_pool, stub_session_pool)

    def _make_first_model_repository(self):
        external_repository = FirstModelRepository("http://localhost:%s" % self.mock_server_port)
        internal_repository = InMemoryRepository(export_first_model)
        return CompositeRepository[FirstModel](external_repository, internal_repository)

    def _make_second_model_repository(self):
        external_repository = SecondModelRepository("http://localhost:%s" % self.mock_server_port)
        internal_repository = InMemoryRepository(export_second_model)
        return CompositeRepository[SecondModel](external_repository, internal_repository)

    def _make_third_model_repository(self):
        external_repository = ThirdModelRepository("http://localhost:%s" % self.mock_server_port)
        internal_repository = InMemoryRepository(export_third_model)
        return CompositeRepository[ThirdModel](external_repository, internal_repository)
