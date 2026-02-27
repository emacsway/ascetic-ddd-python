"""Tests for QueryResolvableSpecification."""
import dataclasses
import typing
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.option import Some
from ascetic_ddd.faker.domain.providers.aggregate_provider import AggregateProvider, IAggregateRepository
from ascetic_ddd.faker.domain.providers.reference_provider import ReferenceProvider
from ascetic_ddd.faker.domain.providers.value_provider import ValueProvider
from ascetic_ddd.faker.domain.query.operators import (
    EqOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.query_resolvable_specification import QueryResolvableSpecification
from ascetic_ddd.faker.infrastructure.repositories.in_memory_repository import InMemoryRepository
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.signals.signal import AsyncSignal
from ascetic_ddd.faker.domain.distributors.m2o.events import ValueAppendedEvent
from ascetic_ddd.faker.domain.providers.events import AggregateInsertedEvent, AggregateUpdatedEvent


# =============================================================================
# Test Fixtures
# =============================================================================

class MockSession:
    """Mock session for testing."""
    pass


@dataclasses.dataclass
class MockObject:
    """Mock object with attributes for RelOperator testing."""
    status: str
    name: str


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


class StubRepository(IAggregateRepository):
    """Stub repository for testing."""

    def __init__(self):
        self._storage = {}
        self._on_inserted = AsyncSignal[AggregateInsertedEvent]()
        self._on_updated = AsyncSignal[AggregateUpdatedEvent]()

    # Signal properties
    @property
    def on_inserted(self):
        return self._on_inserted

    @property
    def on_updated(self):
        return self._on_updated

    async def insert(self, session: ISession, agg):
        key = self._get_key(agg)
        self._storage[key] = agg

    async def get(self, session: ISession, id_) -> typing.Any:
        key = self._extract_key(id_)
        return self._storage.get(key)

    async def update(self, session: ISession, agg):
        key = self._get_key(agg)
        self._storage[key] = agg

    async def find(self, session: ISession, specification: ISpecification):
        return list(self._storage.values())

    async def setup(self, session: ISession):
        pass

    async def cleanup(self, session: ISession):
        self._storage.clear()

    def _get_key(self, agg):
        if hasattr(agg, 'id'):
            return self._extract_key(agg.id)
        return id(agg)

    def _extract_key(self, id_):
        """Extract hashable key from id."""
        if hasattr(id_, 'value'):
            return id_.value
        if isinstance(id_, dict):
            return tuple(sorted(id_.items()))
        return id_


# =============================================================================
# Providers
# =============================================================================

class StatusFaker(AggregateProvider[dict, Status, str, StatusId]):
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
# Tests for resolve_nested()
# =============================================================================

class QueryResolvableSpecificationResolveNestedTestCase(IsolatedAsyncioTestCase):
    """Tests for resolve_nested()."""

    async def test_resolve_nested_without_accessor(self):
        """Without accessor, resolved_query equals original query."""
        query = CompositeQuery({'status': EqOperator('active')})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=None
        )
        session = MockSession()
        await spec.resolve_nested(session)
        self.assertIs(spec._resolved_query, query)

    async def test_resolve_nested_idempotent(self):
        """Calling resolve_nested() multiple times is idempotent."""
        query = CompositeQuery({'status': EqOperator('active')})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=None
        )
        session = MockSession()
        await spec.resolve_nested(session)
        first_resolved = spec._resolved_query

        await spec.resolve_nested(session)
        second_resolved = spec._resolved_query

        self.assertIs(first_resolved, second_resolved)

    async def test_resolve_nested_preserves_eq_operator(self):
        """EqOperator is preserved during resolution."""
        query = EqOperator('active')
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=lambda: None
        )
        session = MockSession()
        await spec.resolve_nested(session)
        self.assertEqual(spec._resolved_query, query)

    async def test_resolve_nested_recreates_rel_operator(self):
        """RelOperator is recreated with resolved constraints."""
        query = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=lambda: None
        )
        session = MockSession()
        await spec.resolve_nested(session)

        # Should be a new RelOperator (not same object)
        self.assertIsInstance(spec._resolved_query, RelOperator)
        self.assertEqual(
            spec._resolved_query.query.fields['status'],
            EqOperator('active')
        )

    async def test_resolve_nested_recreates_composite_query(self):
        """CompositeQuery is recreated with resolved fields."""
        query = CompositeQuery({'status': EqOperator('active')})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=lambda: None
        )
        session = MockSession()
        await spec.resolve_nested(session)

        self.assertIsInstance(spec._resolved_query, CompositeQuery)
        self.assertEqual(
            spec._resolved_query.fields['status'],
            EqOperator('active')
        )

    async def test_resolve_nested_simple_values_unchanged(self):
        """Simple (non-dict) values should stay unchanged with providers."""
        status_repo = StubRepository()
        status_dist = StubDistributor(raise_cursor=True)
        status_provider = StatusFaker(status_repo, status_dist)
        status_provider.provider_name = "status"

        user_repo = StubRepository()
        user_dist = StubDistributor(raise_cursor=True)
        user_provider = UserFaker(user_repo, user_dist, status_provider)
        user_provider.provider_name = "user"

        # Query with simple values (no nested constraints)
        query = QueryParser().parse({'name': 'Alice', 'id': 123})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=lambda: user_provider
        )

        session = MockSession()
        await spec.resolve_nested(session)

        # Simple values should be unchanged
        self.assertIsInstance(spec._resolved_query, CompositeQuery)
        self.assertEqual(spec._resolved_query.fields['name'], EqOperator('Alice'))
        self.assertEqual(spec._resolved_query.fields['id'], EqOperator(123))


# =============================================================================
# Tests for is_satisfied_by()
# =============================================================================

class QueryResolvableSpecificationIsSatisfiedByTestCase(IsolatedAsyncioTestCase):
    """Tests for is_satisfied_by()."""

    async def test_is_satisfied_by_unresolved_raises(self):
        """is_satisfied_by() on unresolved spec raises TypeError."""
        spec = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        session = MockSession()
        with self.assertRaises(TypeError) as ctx:
            await spec.is_satisfied_by(session, {'status': 'active'})
        self.assertIn("unresolved", str(ctx.exception))

    async def test_is_satisfied_by_uses_exporter(self):
        """is_satisfied_by() uses object_exporter."""
        spec = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: {'status': obj.status}  # exporter extracts status
        )
        session = MockSession()
        await spec.resolve_nested(session)

        obj = MockObject(status='active', name='test')
        self.assertTrue(await spec.is_satisfied_by(session, obj))

    async def test_is_satisfied_by_match(self):
        """is_satisfied_by() returns True on match."""
        spec = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        session = MockSession()
        await spec.resolve_nested(session)
        self.assertTrue(await spec.is_satisfied_by(session, {'status': 'active'}))

    async def test_is_satisfied_by_no_match(self):
        """is_satisfied_by() returns False on no match."""
        spec = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        session = MockSession()
        await spec.resolve_nested(session)
        self.assertFalse(await spec.is_satisfied_by(session, {'status': 'inactive'}))


# =============================================================================
# Tests for __hash__, __eq__, __str__
# =============================================================================

class QueryResolvableSpecificationHashEqStrTestCase(IsolatedAsyncioTestCase):
    """Tests for __hash__, __eq__, __str__."""

    def test_hash_unresolved_raises(self):
        """hash() on unresolved spec raises TypeError."""
        spec = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        with self.assertRaises(TypeError) as ctx:
            hash(spec)
        self.assertIn("unresolved", str(ctx.exception))

    async def test_hash_resolved(self):
        """hash() works on resolved spec."""
        spec = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        session = MockSession()
        await spec.resolve_nested(session)
        h = hash(spec)
        self.assertIsInstance(h, int)

    async def test_hash_equality(self):
        """Same resolved query produces same hash."""
        spec1 = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        spec2 = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        session = MockSession()
        await spec1.resolve_nested(session)
        await spec2.resolve_nested(session)
        self.assertEqual(hash(spec1), hash(spec2))

    async def test_hash_inequality(self):
        """Different resolved query produces different hash."""
        spec1 = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        spec2 = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('inactive')}),
            lambda obj: obj
        )
        session = MockSession()
        await spec1.resolve_nested(session)
        await spec2.resolve_nested(session)
        self.assertNotEqual(hash(spec1), hash(spec2))

    def test_eq_unresolved_raises(self):
        """__eq__ on unresolved specs raises TypeError."""
        spec1 = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        spec2 = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        with self.assertRaises(TypeError) as ctx:
            spec1 == spec2
        self.assertIn("unresolved", str(ctx.exception))

    async def test_eq_resolved_same(self):
        """__eq__ returns True for same resolved query."""
        spec1 = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        spec2 = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        session = MockSession()
        await spec1.resolve_nested(session)
        await spec2.resolve_nested(session)
        self.assertEqual(spec1, spec2)

    async def test_eq_resolved_different(self):
        """__eq__ returns False for different resolved query."""
        spec1 = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        spec2 = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('inactive')}),
            lambda obj: obj
        )
        session = MockSession()
        await spec1.resolve_nested(session)
        await spec2.resolve_nested(session)
        self.assertNotEqual(spec1, spec2)

    def test_eq_with_non_specification(self):
        """__eq__ with non-QueryResolvableSpecification returns False."""
        spec = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        self.assertFalse(spec == "not a spec")
        self.assertFalse(spec == None)
        self.assertFalse(spec == 42)

    def test_str_unresolved_raises(self):
        """str() on unresolved spec raises TypeError."""
        spec = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        with self.assertRaises(TypeError) as ctx:
            str(spec)
        self.assertIn("unresolved", str(ctx.exception))

    async def test_str_resolved(self):
        """str() works on resolved spec."""
        spec = QueryResolvableSpecification(
            CompositeQuery({'status': EqOperator('active')}),
            lambda obj: obj
        )
        session = MockSession()
        await spec.resolve_nested(session)
        s = str(spec)
        self.assertIsInstance(s, str)
        self.assertIn('status', s)


# =============================================================================
# Tests for accept()
# =============================================================================

class QueryResolvableSpecificationAcceptTestCase(IsolatedAsyncioTestCase):
    """Tests for accept()."""

    def test_accept_passes_query_and_accessor(self):
        """accept() passes query and accessor to visitor."""
        received = {}

        class MockVisitor:
            def visit_query_specification(self, query, accessor=None):
                received['query'] = query
                received['accessor'] = accessor

        query = CompositeQuery({'status': EqOperator('active')})
        accessor = lambda: "test_provider"
        spec = QueryResolvableSpecification(query, lambda obj: obj, accessor)

        spec.accept(MockVisitor())

        self.assertIs(received['query'], query)
        self.assertIs(received['accessor'], accessor)

    def test_accept_passes_none_when_no_accessor(self):
        """accept() should pass None when no accessor provided."""
        received = {}

        class MockVisitor:
            def visit_query_specification(self, query, accessor=None):
                received['accessor'] = accessor

        query = CompositeQuery({'status': EqOperator('active')})
        spec = QueryResolvableSpecification(query, lambda obj: obj, aggregate_provider_accessor=None)

        spec.accept(MockVisitor())

        self.assertIsNone(received['accessor'])

    async def test_accept_uses_resolved_query_when_available(self):
        """accept() uses resolved_query when available."""
        received = {}

        class MockVisitor:
            def visit_query_specification(self, query, accessor=None):
                received['query'] = query

        query = CompositeQuery({'status': EqOperator('active')})
        spec = QueryResolvableSpecification(query, lambda obj: obj, lambda: None)

        session = MockSession()
        await spec.resolve_nested(session)

        spec.accept(MockVisitor())

        # Should be resolved_query, not original query
        self.assertIs(received['query'], spec._resolved_query)

    def test_accept_uses_original_query_when_unresolved(self):
        """accept() uses original query when not resolved."""
        received = {}

        class MockVisitor:
            def visit_query_specification(self, query, accessor=None):
                received['query'] = query

        query = CompositeQuery({'status': EqOperator('active')})
        spec = QueryResolvableSpecification(query, lambda obj: obj)

        spec.accept(MockVisitor())

        self.assertIs(received['query'], query)


# =============================================================================
# Integration with QueryParser
# =============================================================================

class QueryResolvableSpecificationParserIntegrationTestCase(IsolatedAsyncioTestCase):
    """Integration tests with QueryParser."""

    async def test_with_parsed_simple_query(self):
        """QueryResolvableSpecification works with QueryParser output."""
        query = QueryParser().parse({'status': 'active'})
        spec = QueryResolvableSpecification(query, lambda obj: obj)

        session = MockSession()
        await spec.resolve_nested(session)

        self.assertTrue(await spec.is_satisfied_by(session, {'status': 'active'}))
        self.assertFalse(await spec.is_satisfied_by(session, {'status': 'inactive'}))

    async def test_with_parsed_nested_query(self):
        """
        Nested pattern matching for embedded value objects.

        Covers QueryResolvableSpecification.test_is_satisfied_by_nested_pattern:

            query = QueryParser().parse({'address': {'city': 'Moscow'}})
            spec.is_satisfied_by(session, {'address': {'city': 'Moscow', 'street': 'Main'}})  # True
            spec.is_satisfied_by(session, {'address': {'city': 'London'}})  # False
        """
        query = QueryParser().parse({
            'address': {'city': 'Moscow', 'zip': '123456'}
        })
        spec = QueryResolvableSpecification(query, lambda obj: obj)

        session = MockSession()
        await spec.resolve_nested(session)

        state = {'address': {'city': 'Moscow', 'zip': '123456', 'street': 'Main'}}
        self.assertTrue(await spec.is_satisfied_by(session, state))

        state_wrong = {'address': {'city': 'London', 'zip': '123456'}}
        self.assertFalse(await spec.is_satisfied_by(session, state_wrong))

    async def test_with_parsed_rel_query(self):
        """QueryResolvableSpecification works with $rel queries."""
        query = QueryParser().parse({'$rel': {'status': 'active'}})
        spec = QueryResolvableSpecification(query, lambda obj: obj)

        session = MockSession()
        await spec.resolve_nested(session)

        self.assertTrue(await spec.is_satisfied_by(session, {'status': 'active'}))


# =============================================================================
# Sociable Tests - with real collaborators
# =============================================================================

class QueryResolvableSpecificationCascadeResolutionTestCase(IsolatedAsyncioTestCase):
    """Tests for cascade resolution via ReferenceProviders."""

    async def test_resolve_nested_via_reference_provider(self):
        """Nested constraints are resolved via ReferenceProvider."""
        session = MockSession()
        status_repo = StubRepository()
        active_status = Status(StatusId("active"), "Active")
        await status_repo.insert(session, active_status)

        # raise_cursor=True forces creation of new values via input_generator
        status_dist = StubDistributor(raise_cursor=True)
        status_provider = StatusFaker(status_repo, status_dist)
        status_provider.provider_name = "status"

        user_repo = StubRepository()
        user_dist = StubDistributor(raise_cursor=True)
        user_provider = UserFaker(user_repo, user_dist, status_provider)
        user_provider.provider_name = "user"

        # Test: nested constraint {'name': 'Active'} should resolve to status_id
        query = QueryParser().parse({'status_id': {'$rel': {'name': {'$eq': 'Active'}}}})
        spec = QueryResolvableSpecification(
            query,
            UserFaker._export,
            aggregate_provider_accessor=lambda: user_provider
        )

        await spec.resolve_nested(session)

        # The resolved query should have status_id resolved to the actual ID
        self.assertIsInstance(spec._resolved_query, CompositeQuery)
        resolved_status = spec._resolved_query.fields.get('status_id')
        self.assertIsNotNone(resolved_status)


class QueryResolvableSpecificationSociableTestCase(IsolatedAsyncioTestCase):
    """Sociable tests with real collaborators (InMemoryRepository, real providers)."""

    async def asyncSetUp(self):
        """Set up real repositories and providers."""
        self.session = MockSession()

        # Real repositories
        self.status_repo = InMemoryRepository(
            agg_exporter=StatusFaker._export,
            id_attr='id',
        )
        self.user_repo = InMemoryRepository(
            agg_exporter=UserFaker._export,
            id_attr='id',
        )

        await self.status_repo.setup(self.session)
        await self.user_repo.setup(self.session)

        # Real providers with StubDistributor (external dependency)
        self.status_dist = StubDistributor(raise_cursor=True)
        self.status_provider = StatusFaker(self.status_repo, self.status_dist)
        self.status_provider.provider_name = "status"

        self.user_dist = StubDistributor(raise_cursor=True)
        self.user_provider = UserFaker(self.user_repo, self.user_dist, self.status_provider)
        self.user_provider.provider_name = "user"

    async def asyncTearDown(self):
        """Cleanup repositories."""
        await self.status_repo.cleanup(self.session)
        await self.user_repo.cleanup(self.session)

    async def test_simple_pattern_with_real_providers(self):
        """Simple patterns work with real providers."""
        user = User(UserId(1), StatusId("active"), "Alice")
        await self.user_repo.insert(self.session, user)

        query = QueryParser().parse({'name': 'Alice'})
        spec = QueryResolvableSpecification(
            query,
            UserFaker._export,
            aggregate_provider_accessor=lambda: self.user_provider
        )

        await spec.resolve_nested(self.session)

        self.assertTrue(await spec.is_satisfied_by(self.session, user))

        user2 = User(UserId(2), StatusId("active"), "Bob")
        self.assertFalse(await spec.is_satisfied_by(self.session, user2))

    async def test_repository_find_with_specification(self):
        """InMemoryRepository.find() works with specification."""
        user1 = User(UserId(1), StatusId("active"), "Alice")
        user2 = User(UserId(2), StatusId("inactive"), "Bob")
        user3 = User(UserId(3), StatusId("active"), "Alice")
        await self.user_repo.insert(self.session, user1)
        await self.user_repo.insert(self.session, user2)
        await self.user_repo.insert(self.session, user3)

        query = QueryParser().parse({'name': 'Alice'})
        spec = QueryResolvableSpecification(
            query,
            UserFaker._export,
            aggregate_provider_accessor=lambda: self.user_provider
        )

        await spec.resolve_nested(self.session)

        found = [u async for u in self.user_repo.find(self.session, spec)]

        self.assertEqual(len(found), 2)
        names = [u.name for u in found]
        self.assertIn('Alice', names)
        self.assertNotIn('Bob', names)


if __name__ == '__main__':
    import unittest
    unittest.main()
