"""Tests for QueryLookupSpecification."""
import dataclasses
import typing
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.option import Some
from ascetic_ddd.faker.domain.providers.aggregate_provider import AggregateProvider, IAggregateRepository
from ascetic_ddd.faker.domain.providers.interfaces import IReferenceProvider
from ascetic_ddd.faker.domain.providers.reference_provider import ReferenceProvider
from ascetic_ddd.faker.domain.providers.value_provider import ValueProvider
from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.query_lookup_specification import (
    QueryLookupSpecification
)
from ascetic_ddd.faker.infrastructure.repositories.in_memory_repository import InMemoryRepository
from ascetic_ddd.signals.signal import AsyncSignal, SyncSignal
from ascetic_ddd.faker.domain.distributors.m2o.events import ValueAppendedEvent
from ascetic_ddd.faker.domain.providers.events import CriteriaRequiredEvent, InputPopulatedEvent


# =============================================================================
# Test Fixtures
# =============================================================================

@dataclasses.dataclass(frozen=True)
class StatusId:
    value: str


@dataclasses.dataclass
class Status:
    id: StatusId
    name: str


@dataclasses.dataclass(frozen=True)
class UserId:
    value: int


@dataclasses.dataclass
class User:
    id: UserId
    status_id: StatusId
    name: str


@dataclasses.dataclass(frozen=True)
class CompanyId:
    value: str


@dataclasses.dataclass
class Company:
    id: CompanyId
    owner_id: UserId
    name: str


class MockSession:
    """Mock session for testing."""
    pass


class StubDistributor(IM2ODistributor):
    """Stub distributor that returns predefined values."""

    def __init__(self, values: list = None, raise_cursor: bool = False):
        self._values = values or []
        self._index = 0
        self._raise_cursor = raise_cursor
        self._appended = []
        self._provider_name = None
        self._on_appended = AsyncSignal[ValueAppendedEvent]()

    async def next(self, session: ISession, specification: ISpecification = None):
        if self._raise_cursor or self._index >= len(self._values):
            raise Cursor(position=self._index, callback=self._append)
        value = self._values[self._index]
        self._index += 1
        return Some(value)

    async def _append(self, session: ISession, value, position):
        self._appended.append(value)

    async def append(self, session: ISession, value):
        self._appended.append(value)

    # Signal properties
    @property
    def on_appended(self):
        return self._on_appended

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._provider_name = value

    async def setup(self, session: ISession):
        pass

    async def cleanup(self, session: ISession):
        pass

    def bind_external_source(self, external_source: typing.Any) -> None:
        pass

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self


class MockRepository:
    """Mock async repository for testing."""

    def __init__(self, storage: dict = None):
        self._storage = storage or {}

    async def get(self, session, id_):
        key = self._extract_key(id_)
        return self._storage.get(key)

    def _extract_key(self, id_):
        if hasattr(id_, 'value'):
            return id_.value
        return id_

    def add(self, obj):
        if hasattr(obj, 'id'):
            key = self._extract_key(obj.id)
            self._storage[key] = obj


class MockReferenceProvider(IReferenceProvider):
    """Mock reference provider for testing."""

    def __init__(self, repository: MockRepository, aggregate_provider: typing.Any):
        self._repository = repository
        self._aggregate_provider = aggregate_provider
        self._query = None
        self._output = None
        self._output_defined = False
        self._provider_name = None
        self._on_required = SyncSignal[CriteriaRequiredEvent]()
        self._on_populated = SyncSignal[InputPopulatedEvent]()

    # Signal properties
    @property
    def on_required(self):
        return self._on_required

    @property
    def on_populated(self):
        return self._on_populated

    @property
    def aggregate_provider(self):
        return self._aggregate_provider

    @aggregate_provider.setter
    def aggregate_provider(self, value):
        self._aggregate_provider = value

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._provider_name = value

    async def populate(self, session):
        pass

    def require(self, value):
        self._query = value

    def state(self):
        return self._output

    def output(self):
        return self._output

    async def append(self, session, value):
        pass

    def reset(self):
        self._query = None
        self._output = None
        self._output_defined = False

    def is_complete(self):
        return self._output_defined

    def is_transient(self):
        return self._query is None

    def clone(self, shunt=None):
        return MockReferenceProvider(self._repository, self._aggregate_provider)

    def do_clone(self, clone, shunt):
        pass

    async def setup(self, session):
        pass

    async def cleanup(self, session):
        pass


class MockAggregateProvider:
    """Mock aggregate provider for testing."""

    def __init__(
            self,
            providers: dict = None,
            output_exporter: typing.Callable = None,
            repository: typing.Any = None
    ):
        self._providers = providers or {}
        self._output_exporter = output_exporter or (lambda x: x)
        self.repository = repository

    @property
    def providers(self):
        return self._providers


# =============================================================================
# Real Providers for Sociable Tests
# =============================================================================

class StatusFaker(AggregateProvider[dict, Status, str, StatusId]):
    """Real StatusFaker provider for sociable tests."""
    _id_attr = 'id'

    id: ValueProvider[str, StatusId]
    name: ValueProvider[str, str]

    def __init__(self, repository: IAggregateRepository, distributor: IM2ODistributor):
        self.id = ValueProvider(
            distributor=distributor,
            input_generator=lambda session, query=None, pos=None: "status_%s" % (pos or 0),
            output_factory=StatusId,
        )
        self.name = ValueProvider(
            distributor=StubDistributor(values=["Active", "Inactive", "Pending"]),
            input_generator=lambda session, query=None, pos=None: "Status %s" % (pos or 0),
        )
        super().__init__(
            repository=repository,
            output_factory=Status,
            output_exporter=self._export,
        )

    @staticmethod
    def _export(status: Status) -> dict:
        return {
            'id': status.id.value if hasattr(status.id, 'value') else status.id,
            'name': status.name,
        }


class UserFaker(AggregateProvider[dict, User, int, UserId]):
    """Real UserFaker provider for sociable tests."""
    _id_attr = 'id'

    id: ValueProvider[int, UserId]
    status_id: ReferenceProvider
    name: ValueProvider[str, str]

    def __init__(
            self,
            repository: IAggregateRepository,
            distributor: IM2ODistributor,
            status_provider: StatusFaker
    ):
        self.id = ValueProvider(
            distributor=StubDistributor(raise_cursor=True),
            input_generator=lambda session, query=None, pos=None: pos or 1,
            output_factory=UserId,
        )
        self.status_id = ReferenceProvider(
            distributor=distributor,
            aggregate_provider=status_provider,
        )
        self.name = ValueProvider(
            distributor=StubDistributor(values=["Alice", "Bob", "Charlie"]),
            input_generator=lambda session, query=None, pos=None: "User %s" % (pos or 0),
        )
        super().__init__(
            repository=repository,
            output_factory=User,
            output_exporter=self._export,
        )

    @staticmethod
    def _export(user: User) -> dict:
        return {
            'id': user.id.value if hasattr(user.id, 'value') else user.id,
            'status_id': user.status_id.value if hasattr(user.status_id, 'value') else user.status_id,
            'name': user.name,
        }


# =============================================================================
# Tests for QueryLookupSpecification - Basic
# =============================================================================

class QueryLookupSpecificationBasicTestCase(IsolatedAsyncioTestCase):
    """Basic tests for QueryLookupSpecification."""

    async def test_is_satisfied_by_simple_pattern_without_provider(self):
        """Simple pattern matching without provider should work."""
        query = QueryParser().parse({'status': 'active'})
        spec = QueryLookupSpecification(
            query,
            lambda obj: obj
        )
        self.assertTrue(await spec.is_satisfied_by(None, {'status': 'active', 'name': 'test'}))
        self.assertFalse(await spec.is_satisfied_by(None, {'status': 'inactive', 'name': 'test'}))

    async def test_is_satisfied_by_nested_pattern_without_provider(self):
        """Nested pattern without provider should use simple subset check."""
        query = QueryParser().parse({'address': {'city': 'Moscow'}})
        spec = QueryLookupSpecification(
            query,
            lambda obj: obj
        )
        self.assertTrue(await spec.is_satisfied_by(None, {'address': {'city': 'Moscow', 'street': 'Main'}}))
        self.assertFalse(await spec.is_satisfied_by(None, {'address': {'city': 'London'}}))

    def test_hash_uses_query(self):
        """hash() should use query directly."""
        query = QueryParser().parse({'status': 'active'})
        spec = QueryLookupSpecification(
            query,
            lambda obj: obj
        )

        self.assertEqual(hash(spec), hash(query))

    def test_hash_equality(self):
        """Specifications with same query should have equal hash."""
        query1 = QueryParser().parse({'status': 'active'})
        query2 = QueryParser().parse({'status': 'active'})
        spec1 = QueryLookupSpecification(query1, lambda obj: obj)
        spec2 = QueryLookupSpecification(query2, lambda obj: obj)
        self.assertEqual(hash(spec1), hash(spec2))

    def test_hash_inequality(self):
        """Specifications with different query should have different hash."""
        query1 = QueryParser().parse({'status': 'active'})
        query2 = QueryParser().parse({'status': 'inactive'})
        spec1 = QueryLookupSpecification(query1, lambda obj: obj)
        spec2 = QueryLookupSpecification(query2, lambda obj: obj)
        self.assertNotEqual(hash(spec1), hash(spec2))

    def test_eq_uses_query(self):
        """__eq__ should compare query value."""
        query1 = QueryParser().parse({'status': 'active'})
        query2 = QueryParser().parse({'status': 'active'})
        spec1 = QueryLookupSpecification(query1, lambda obj: obj)
        spec2 = QueryLookupSpecification(query2, lambda obj: obj)
        self.assertEqual(spec1, spec2)

    def test_eq_different_queries(self):
        """Specifications with different query should not be equal."""
        query1 = QueryParser().parse({'status': 'active'})
        query2 = QueryParser().parse({'status': 'inactive'})
        spec1 = QueryLookupSpecification(query1, lambda obj: obj)
        spec2 = QueryLookupSpecification(query2, lambda obj: obj)
        self.assertNotEqual(spec1, spec2)

    def test_eq_with_non_specification(self):
        """__eq__ with non-QueryLookupSpecification should return False."""
        query = QueryParser().parse({'status': 'active'})
        spec = QueryLookupSpecification(query, lambda obj: obj)
        self.assertNotEqual(spec, {'status': 'active'})
        self.assertNotEqual(spec, "string")
        self.assertNotEqual(spec, 123)


# =============================================================================
# Tests for QueryLookupSpecification - Nested Lookup
# =============================================================================

class QueryLookupSpecificationNestedLookupTestCase(IsolatedAsyncioTestCase):
    """Tests for nested lookup in is_satisfied_by()."""

    def setUp(self):
        # Setup Status aggregate
        self.status_active = Status(StatusId("active"), "Active")
        self.status_inactive = Status(StatusId("inactive"), "Inactive")

        self.status_repo = MockRepository()
        self.status_repo.add(self.status_active)
        self.status_repo.add(self.status_inactive)

        self.status_provider = MockAggregateProvider(
            output_exporter=lambda s: {'id': s.id.value, 'name': s.name},
            repository=self.status_repo
        )

        # Setup User aggregate with reference to Status
        self.user_alice = User(UserId(1), StatusId("active"), "Alice")
        self.user_bob = User(UserId(2), StatusId("inactive"), "Bob")

        self.user_repo = MockRepository()
        self.user_repo.add(self.user_alice)
        self.user_repo.add(self.user_bob)

        self.status_ref_provider = MockReferenceProvider(
            self.status_repo, self.status_provider
        )

        self.user_provider = MockAggregateProvider(
            providers={'status_id': self.status_ref_provider},
            output_exporter=lambda u: {'id': u.id.value, 'status_id': u.status_id.value, 'name': u.name},
            repository=self.user_repo
        )
        self.session = MockSession()

    async def test_nested_lookup_matches(self):
        """Nested lookup should match when foreign object satisfies pattern."""
        query = QueryParser().parse({'status_id': {'$rel': {'name': 'Active'}}})
        spec = QueryLookupSpecification(
            query,
            lambda u: {'id': u.id.value, 'status_id': u.status_id.value, 'name': u.name},
            aggregate_provider_accessor=lambda: self.user_provider
        )

        # Alice has active status
        self.assertTrue(await spec.is_satisfied_by(self.session, self.user_alice))
        # Bob has inactive status
        self.assertFalse(await spec.is_satisfied_by(self.session, self.user_bob))

    async def test_nested_lookup_returns_false_when_fk_is_none(self):
        """Nested lookup should return False when fk_id is None."""
        query = QueryParser().parse({'status_id': {'$rel': {'name': 'Active'}}})
        spec = QueryLookupSpecification(
            query,
            lambda u: {'id': u.id.value, 'status_id': None, 'name': u.name},
            aggregate_provider_accessor=lambda: self.user_provider
        )

        self.assertFalse(await spec.is_satisfied_by(self.session, self.user_alice))

    async def test_nested_lookup_returns_false_when_foreign_obj_not_found(self):
        """Nested lookup should return False when foreign object not found."""
        user_with_unknown_status = User(UserId(3), StatusId("unknown"), "Charlie")

        query = QueryParser().parse({'status_id': {'$rel': {'name': 'Active'}}})
        spec = QueryLookupSpecification(
            query,
            lambda u: {'id': u.id.value, 'status_id': u.status_id.value, 'name': u.name},
            aggregate_provider_accessor=lambda: self.user_provider
        )

        self.assertFalse(await spec.is_satisfied_by(self.session, user_with_unknown_status))

    async def test_simple_value_comparison_with_provider(self):
        """Simple value comparison should work alongside nested lookup."""
        query = QueryParser().parse({'name': 'Alice', 'status_id': {'$rel': {'name': 'Active'}}})
        spec = QueryLookupSpecification(
            query,
            lambda u: {'id': u.id.value, 'status_id': u.status_id.value, 'name': u.name},
            aggregate_provider_accessor=lambda: self.user_provider
        )

        # Alice matches both name and status
        self.assertTrue(await spec.is_satisfied_by(self.session, self.user_alice))
        # Bob doesn't match name
        self.assertFalse(await spec.is_satisfied_by(self.session, self.user_bob))


# =============================================================================
# Tests for QueryLookupSpecification - Accept
# =============================================================================

class QueryLookupSpecificationAcceptTestCase(IsolatedAsyncioTestCase):
    """Tests for accept() method."""

    def test_accept_passes_query(self):
        """accept() should pass query to visitor."""
        received_query = [None]

        class MockVisitor:
            def visit_query_specification(self, query, accessor=None):
                received_query[0] = query

        query = QueryParser().parse({'status_id': {'name': 'Active'}})
        spec = QueryLookupSpecification(
            query,
            lambda obj: obj
        )

        visitor = MockVisitor()
        spec.accept(visitor)

        self.assertEqual(received_query[0], query)

    def test_accept_passes_aggregate_provider_accessor(self):
        """accept() should pass aggregate_provider_accessor to visitor."""
        received_accessor = [None]

        class MockVisitor:
            def visit_query_specification(self, query, accessor=None):
                received_accessor[0] = accessor

        accessor = lambda: "test_provider"
        query = QueryParser().parse({'status': 'active'})
        spec = QueryLookupSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=accessor
        )

        visitor = MockVisitor()
        spec.accept(visitor)

        self.assertIs(received_accessor[0], accessor)


# =============================================================================
# Sociable Tests - Using Real Providers
# =============================================================================

class QueryLookupSpecificationSociableTestCase(IsolatedAsyncioTestCase):
    """
    Sociable tests using real AggregateProvider and ReferenceProvider.

    These tests verify that QueryLookupSpecification works correctly
    with the real provider infrastructure, not just mocks.
    """

    def setUp(self):
        # Create repositories using real InMemoryRepository
        self.status_repo = InMemoryRepository(
            agg_exporter=StatusFaker._export,
            id_attr='id'
        )
        self.user_repo = InMemoryRepository(
            agg_exporter=UserFaker._export,
            id_attr='id'
        )
        self.session = MockSession()

        # Create real StatusFaker provider
        self.status_distributor = StubDistributor(
            values=[
                Status(StatusId("active"), "Active"),
                Status(StatusId("inactive"), "Inactive"),
            ]
        )
        self.status_provider = StatusFaker(self.status_repo, self.status_distributor)
        self.status_provider.provider_name = "status"

        # Create real UserFaker provider with ReferenceProvider to Status
        self.user_distributor = StubDistributor()
        self.user_provider = UserFaker(
            self.user_repo,
            self.user_distributor,
            self.status_provider
        )
        self.user_provider.provider_name = "user"

        # Pre-populate repositories with test data
        self.status_active = Status(StatusId("active"), "Active")
        self.status_inactive = Status(StatusId("inactive"), "Inactive")

        self.user_alice = User(UserId(1), StatusId("active"), "Alice")
        self.user_bob = User(UserId(2), StatusId("inactive"), "Bob")

    async def asyncSetUp(self):
        await super().asyncSetUp()
        session = MockSession()

        # Insert statuses into real InMemoryRepository
        await self.status_repo.insert(session, self.status_active)
        await self.status_repo.insert(session, self.status_inactive)

        # Insert users
        await self.user_repo.insert(session, self.user_alice)
        await self.user_repo.insert(session, self.user_bob)

    async def test_nested_lookup_with_real_providers(self):
        """Nested lookup should work with real AggregateProvider and ReferenceProvider."""
        query = QueryParser().parse({'status_id': {'$rel': {'name': 'Active'}}})
        spec = QueryLookupSpecification(
            query,
            UserFaker._export,
            aggregate_provider_accessor=lambda: self.user_provider
        )

        # Alice has active status - should match
        self.assertTrue(await spec.is_satisfied_by(self.session, self.user_alice))

        # Bob has inactive status - should not match
        self.assertFalse(await spec.is_satisfied_by(self.session, self.user_bob))

    async def test_combined_pattern_with_real_providers(self):
        """Combined simple and nested pattern should work with real providers."""
        query = QueryParser().parse({'name': 'Alice', 'status_id': {'$rel': {'name': 'Active'}}})
        spec = QueryLookupSpecification(
            query,
            UserFaker._export,
            aggregate_provider_accessor=lambda: self.user_provider
        )

        # Alice matches both name and status
        self.assertTrue(await spec.is_satisfied_by(self.session, self.user_alice))

        # Bob doesn't match name
        self.assertFalse(await spec.is_satisfied_by(self.session, self.user_bob))


if __name__ == '__main__':
    import unittest
    unittest.main()
