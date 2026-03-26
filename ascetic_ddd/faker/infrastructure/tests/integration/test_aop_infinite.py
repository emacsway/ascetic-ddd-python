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
from ascetic_ddd.faker.domain.aop.providers.value_provider import ValueProvider
from ascetic_ddd.faker.domain.aop.providers.structure_provider import StructureProvider
from ascetic_ddd.faker.domain.aop.providers.modeled_provider import ModeledProvider
from ascetic_ddd.faker.domain.aop.providers.persisted_provider import PersistedProvider
from ascetic_ddd.faker.domain.aop.providers.distributed_provider import DistributedProvider
from ascetic_ddd.faker.domain.aop.providers.pipe import Pipe, PipeStep
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


# ################## Faker Factories (Pipe-based) #######################
#
# With Pipe, FK values flow top-down via require_fn.
# No ReferenceProvider needed — parent is created first,
# its ID is passed to child via pipe context.
#


def make_first_model_faker(repository, make_distributor):
    """FirstModel provider — no FK references, unchanged."""
    id_prov = ValueProvider()
    attr2_prov = DistributedProvider(
        ValueProvider(input_generator=Attr2ValueGenerator()),
        distributor=make_distributor(
            weights=[0.9, 0.5, 0.1, 0.01],
            mean=10,
            name='first_model.attr2',
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


def make_second_model_faker(repository, make_distributor):
    """SecondModel provider — FK first_model_id is a plain ValueProvider.

    Value comes from Pipe context via require_fn, not from ReferenceProvider.
    """
    # SecondModelPk providers
    pk_id_prov = ValueProvider()
    # FK value provided by Pipe context — no ReferenceProvider needed
    first_model_id_prov = ValueProvider()
    pk_structure = StructureProvider(
        id=pk_id_prov,
        first_model_id=first_model_id_prov,
    )
    pk_modeled = ModeledProvider(
        pk_structure,
        factory=SecondModelPk,
        exporter=export_second_model_pk,
    )

    # SecondModel providers
    attr2_prov = DistributedProvider(
        ValueProvider(input_generator=Attr2ValueGenerator()),
        distributor=make_distributor(
            weights=[0.9, 0.5, 0.1, 0.01],
            mean=10,
            name='second_model.attr2',
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


def make_third_model_faker(repository, make_distributor):
    """ThirdModel provider — all FK values are plain ValueProviders.

    Values come from Pipe context via require_fn.
    No ThirdModelStructure needed — Pipe handles tenant consistency
    by creating FirstModel first and passing its ID to all downstream steps.
    """
    # ThirdModelPk providers
    pk_id_prov = ValueProvider()
    # FK value provided by Pipe context
    first_model_id_prov = ValueProvider()
    pk_structure = StructureProvider(
        id=pk_id_prov,
        first_model_id=first_model_id_prov,
    )
    pk_modeled = ModeledProvider(
        pk_structure,
        factory=ThirdModelPk,
        exporter=export_third_model_pk,
    )

    # FK to SecondModel — value provided by Pipe context
    second_model_id_prov = ValueProvider()

    attr2_prov = DistributedProvider(
        ValueProvider(input_generator=Attr2ValueGenerator()),
        distributor=make_distributor(
            weights=[0.9, 0.5, 0.1, 0.01],
            mean=10,
            name='third_model.attr2',
        ),
    )

    # Self-reference — always None (same limitation as before)
    parent_id_prov = ValueProvider()

    structure = StructureProvider(
        id=pk_modeled,
        second_model_id=second_model_id_prov,
        attr2=attr2_prov,
        parent_id=parent_id_prov,
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


# ################## Pipe require_fn helpers ############################


def _second_model_require(ctx):
    """Constrain SecondModel's FK to the FirstModel from pipe context."""
    return {
        'id': {'first_model_id': {'$eq': ctx['first_model'].id}}
    }


def _third_model_require(ctx):
    """Constrain ThirdModel's FKs from pipe context.

    - PK.first_model_id = FirstModel from context
    - second_model_id = SecondModel PK from context (or None)
    - parent_id = None (self-reference not supported yet)
    """
    first_model_id = ctx['first_model'].id
    second_model = ctx.get('second_model')
    second_model_id = second_model.id if second_model is not None else None
    return {
        'id': {'first_model_id': {'$eq': first_model_id}},
        'second_model_id': {'$eq': second_model_id},
        'parent_id': {'$eq': None},
    }


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

    async def test_second_model_pipe(self):
        pipe = self._make_second_model_pipe()
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await pipe.setup(ts_session)
            await pipe.populate(ts_session)
            agg = pipe.output()
            self.assertIsInstance(agg.id.id, uuid.UUID)
            self.assertIsInstance(agg.id.first_model_id, uuid.UUID)
            await pipe.cleanup(ts_session)

    async def test_third_model_pipe(self):
        pipe = self._make_third_model_pipe()
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await pipe.setup(ts_session)
            await pipe.populate(ts_session)
            agg = pipe.output()
            self.assertIsInstance(agg.id.id, uuid.UUID)
            self.assertIsInstance(agg.id.first_model_id, uuid.UUID)

            if agg.second_model_id is not None:
                self.assertIsInstance(agg.second_model_id.id, uuid.UUID)
                self.assertIsInstance(agg.second_model_id.first_model_id, uuid.UUID)

            # parent_id is always None (self-reference not supported yet)
            self.assertIsNone(agg.parent_id)
            await pipe.cleanup(ts_session)

    async def test_batch_third_model_pipe(self):
        debug = False
        start_date = datetime.datetime.now()

        if debug:
            profiler = profile.Profile()
            profiler.enable()

        pipe = self._make_third_model_pipe()
        third_model_aggs = []
        async with self.session_pool.session() as session, session.atomic() as ts_session:
            await pipe.setup(ts_session)
            for _ in range(100):
                await pipe.populate(ts_session)
                agg = pipe.output()
                third_model_aggs.append(agg)
                self.assertIsInstance(agg.id.id, uuid.UUID)
                self.assertIsInstance(agg.id.first_model_id, uuid.UUID)

                if agg.second_model_id is not None:
                    self.assertIsInstance(agg.second_model_id.id, uuid.UUID)
                    self.assertIsInstance(agg.second_model_id.first_model_id, uuid.UUID)

                # parent_id is always None
                self.assertIsNone(agg.parent_id)

                pipe.reset()

            await pipe.cleanup(ts_session)

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

    def _make_second_model_pipe(self):
        first_model_faker = self._make_first_model_faker()
        # Pipe-level distributor: controls which FirstModel is selected/created
        first_model_step = DistributedProvider(
            first_model_faker,
            distributor=self.make_distributor(
                weights=[0.9, 0.5, 0.1, 0.01],
                mean=10,
                name='pipe.first_model',
            ),
            object_exporter=export_first_model,
        )
        second_model_faker = make_second_model_faker(
            self._make_second_model_repository(),
            self.make_distributor,
        )
        return Pipe(
            PipeStep('first_model', first_model_step),
            PipeStep('second_model', second_model_faker,
                     require_fn=_second_model_require),
            result='second_model',
        )

    def _make_third_model_pipe(self):
        first_model_faker = self._make_first_model_faker()
        # Pipe-level distributor: controls FirstModel distribution (Zipf)
        first_model_step = DistributedProvider(
            first_model_faker,
            distributor=self.make_distributor(
                weights=[0.9, 0.5, 0.1, 0.01],
                mean=10,
                name='pipe.first_model',
            ),
            object_exporter=export_first_model,
        )
        second_model_faker = make_second_model_faker(
            self._make_second_model_repository(),
            self.make_distributor,
        )
        # Pipe-level distributor: controls SecondModel distribution + nullability
        second_model_step = DistributedProvider(
            second_model_faker,
            distributor=self.make_distributor(
                weights=[0.9, 0.5, 0.1, 0.01],
                null_weight=0.5,
                mean=10,
                name='pipe.second_model',
            ),
            object_exporter=export_second_model,
        )
        third_model_faker = make_third_model_faker(
            self._make_third_model_repository(),
            self.make_distributor,
        )
        return Pipe(
            PipeStep('first_model', first_model_step),
            PipeStep('second_model', second_model_step,
                     require_fn=_second_model_require),
            PipeStep('third_model', third_model_faker,
                     require_fn=_third_model_require),
            result='third_model',
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
