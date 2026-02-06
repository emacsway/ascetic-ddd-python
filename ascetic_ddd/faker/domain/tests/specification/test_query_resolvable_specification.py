"""Tests for QueryResolvableSpecification."""
import dataclasses
import typing
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.faker.domain.providers.aggregate_provider import AggregateProvider, IAggregateRepository
from ascetic_ddd.faker.domain.providers.reference_provider import ReferenceProvider
from ascetic_ddd.faker.domain.providers.value_provider import ValueProvider
from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.faker.domain.query.operators import EqOperator, RelOperator, CompositeQuery
from ascetic_ddd.seedwork.domain.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.domain.specification.query_resolvable_specification import QueryResolvableSpecification
from ascetic_ddd.faker.domain.values.empty import empty
from ascetic_ddd.faker.infrastructure.repositories.in_memory_repository import InMemoryRepository


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
        self._observers = []

    async def next(self, session: ISession, specification: ISpecification = None):
        if self._raise_cursor or self._index >= len(self._values):
            raise Cursor(position=self._index, callback=self._append)
        value = self._values[self._index]
        self._index += 1
        return value

    async def _append(self, session: ISession, value, position):
        self._appended.append(value)

    async def append(self, session: ISession, value):
        self._appended.append(value)

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

    def attach(self, aspect, observer, id_=None):
        self._observers.append((aspect, observer))
        return lambda: self._observers.remove((aspect, observer))

    def detach(self, aspect, observer, id_=None):
        self._observers = [(a, o) for a, o in self._observers if o != observer]

    def notify(self, aspect, *args, **kwargs):
        pass

    async def anotify(self, aspect, *args, **kwargs):
        pass

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self


class StubRepository(IAggregateRepository):
    """Stub repository for testing."""

    def __init__(self):
        self._storage = {}
        self._observers = []

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

    def attach(self, aspect, observer, id_=None):
        self._observers.append((aspect, observer))
        return lambda: self._observers.remove((aspect, observer))

    def detach(self, aspect, observer, id_=None):
        self._observers = [(a, o) for a, o in self._observers if o != observer]

    def notify(self, aspect, *args, **kwargs):
        pass

    async def anotify(self, aspect, *args, **kwargs):
        pass


# =============================================================================
# Providers
# =============================================================================

class StatusFaker(AggregateProvider[dict, Status]):
    _id_attr = 'id'

    id: ValueProvider[str, StatusId]
    name: ValueProvider[str, str]

    def __init__(self, repository: IAggregateRepository, distributor: IM2ODistributor):
        self.id = ValueProvider(
            distributor=distributor,
            input_generator=lambda session, pos=None: "status_%s" % (pos or 0),
            output_factory=StatusId,
        )
        self.name = ValueProvider(
            distributor=StubDistributor(values=["Active", "Inactive", "Pending"]),
            input_generator=lambda session, pos=None: "Status %s" % (pos or 0),
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


class UserFaker(AggregateProvider[dict, User]):
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
            input_generator=lambda session, pos=None: pos or 1,
            output_factory=UserId,
        )
        self.status_id = ReferenceProvider(
            distributor=distributor,
            aggregate_provider=status_provider,
        )
        self.name = ValueProvider(
            distributor=StubDistributor(values=["Alice", "Bob", "Charlie"]),
            input_generator=lambda session, pos=None: "User %s" % (pos or 0),
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
# Tests for QueryResolvableSpecification
# =============================================================================

class QueryResolvableSpecificationBasicTestCase(IsolatedAsyncioTestCase):
    """Basic tests for QueryResolvableSpecification."""

    async def test_is_satisfied_by_simple_pattern(self):
        """Simple pattern matching should work."""
        query = QueryParser().parse({'status': 'active'})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj
        )
        session = MockSession()
        await spec.resolve_nested(session)
        self.assertTrue(await spec.is_satisfied_by(session, {'status': 'active', 'name': 'test'}))
        self.assertFalse(await spec.is_satisfied_by(session, {'status': 'inactive', 'name': 'test'}))

    async def test_is_satisfied_by_nested_pattern(self):
        """Nested pattern matching should work."""
        query = QueryParser().parse({'address': {'city': 'Moscow'}})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj
        )
        session = MockSession()
        await spec.resolve_nested(session)
        self.assertTrue(await spec.is_satisfied_by(session, {'address': {'city': 'Moscow', 'street': 'Main'}}))
        self.assertFalse(await spec.is_satisfied_by(session, {'address': {'city': 'London'}}))

    async def test_is_satisfied_by_unresolved_raises_exception(self):
        """is_satisfied_by() on unresolved specification should raise TypeError."""
        query = QueryParser().parse({'status': 'active'})
        spec = QueryResolvableSpecification(query, lambda obj: obj)
        session = MockSession()
        with self.assertRaises(TypeError) as ctx:
            await spec.is_satisfied_by(session, {'status': 'active'})
        self.assertIn("unresolved", str(ctx.exception))

    async def test_hash_equality(self):
        """Specifications with same resolved pattern should be equal."""
        query1 = QueryParser().parse({'status': 'active'})
        query2 = QueryParser().parse({'status': 'active'})
        spec1 = QueryResolvableSpecification(query1, lambda obj: obj)
        spec2 = QueryResolvableSpecification(query2, lambda obj: obj)
        session = MockSession()
        await spec1.resolve_nested(session)
        await spec2.resolve_nested(session)
        self.assertEqual(hash(spec1), hash(spec2))
        self.assertEqual(spec1, spec2)

    async def test_hash_inequality(self):
        """Specifications with different resolved patterns should not be equal."""
        query1 = QueryParser().parse({'status': 'active'})
        query2 = QueryParser().parse({'status': 'inactive'})
        spec1 = QueryResolvableSpecification(query1, lambda obj: obj)
        spec2 = QueryResolvableSpecification(query2, lambda obj: obj)
        session = MockSession()
        await spec1.resolve_nested(session)
        await spec2.resolve_nested(session)
        self.assertNotEqual(hash(spec1), hash(spec2))
        self.assertNotEqual(spec1, spec2)

    def test_hash_unresolved_raises_exception(self):
        """Hash of unresolved specification should raise TypeError."""
        query = QueryParser().parse({'status': 'active'})
        spec = QueryResolvableSpecification(query, lambda obj: obj)
        with self.assertRaises(TypeError) as ctx:
            hash(spec)
        self.assertIn("unresolved", str(ctx.exception))

    def test_eq_unresolved_raises_exception(self):
        """Comparing unresolved specifications should raise TypeError."""
        query1 = QueryParser().parse({'status': 'active'})
        query2 = QueryParser().parse({'status': 'active'})
        spec1 = QueryResolvableSpecification(query1, lambda obj: obj)
        spec2 = QueryResolvableSpecification(query2, lambda obj: obj)
        with self.assertRaises(TypeError) as ctx:
            spec1 == spec2
        self.assertIn("unresolved", str(ctx.exception))


class QueryResolvableSpecificationResolveNestedTestCase(IsolatedAsyncioTestCase):
    """Tests for QueryResolvableSpecification.resolve_nested()."""

    async def test_resolve_nested_without_accessor(self):
        """Without aggregate_provider_accessor, pattern stays unchanged."""
        query = QueryParser().parse({'status_id': {'name': 'Active'}})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=None
        )

        session = MockSession()
        await spec.resolve_nested(session)

        # Pattern should be unchanged (copied to _resolved_pattern)
        self.assertEqual(spec._resolved_pattern, {'status_id': {'name': 'Active'}})

    async def test_resolve_nested_simple_values_unchanged(self):
        """Simple (non-dict) values should stay unchanged."""
        status_repo = StubRepository()
        status_dist = StubDistributor(values=[Status(StatusId("active"), "Active")])
        status_provider = StatusFaker(status_repo, status_dist)
        status_provider.provider_name = "status"

        user_repo = StubRepository()
        user_dist = StubDistributor()
        user_provider = UserFaker(user_repo, user_dist, status_provider)
        user_provider.provider_name = "user"

        query = QueryParser().parse({'name': 'Alice', 'id': 123})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=lambda: user_provider
        )

        session = MockSession()
        await spec.resolve_nested(session)

        # Simple values should be unchanged
        self.assertEqual(spec._resolved_pattern['name'], 'Alice')
        self.assertEqual(spec._resolved_pattern['id'], 123)

    async def test_resolve_nested_idempotent(self):
        """Calling resolve_nested() multiple times should be idempotent."""
        query = QueryParser().parse({'status': 'active'})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=None
        )

        session = MockSession()
        await spec.resolve_nested(session)
        first_resolved = spec._resolved_pattern

        await spec.resolve_nested(session)
        second_resolved = spec._resolved_pattern

        # Should be the same object (not re-resolved)
        self.assertIs(first_resolved, second_resolved)


class QueryResolvableSpecificationAcceptTestCase(IsolatedAsyncioTestCase):
    """Tests for QueryResolvableSpecification.accept()."""

    def test_accept_passes_aggregate_provider_accessor(self):
        """accept() should pass aggregate_provider_accessor to visitor."""
        received_accessor = [None]

        class MockVisitor:
            def visit_query_specification(self, query, accessor=None):
                received_accessor[0] = accessor

        accessor = lambda: "test_provider"
        query = QueryParser().parse({'status': 'active'})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=accessor
        )

        visitor = MockVisitor()
        spec.accept(visitor)

        self.assertIs(received_accessor[0], accessor)

    def test_accept_passes_none_when_no_accessor(self):
        """accept() should pass None when no accessor provided."""
        received_accessor = ["not_none"]

        class MockVisitor:
            def visit_query_specification(self, query, accessor=None):
                received_accessor[0] = accessor

        query = QueryParser().parse({'status': 'active'})
        spec = QueryResolvableSpecification(
            query,
            lambda obj: obj,
            aggregate_provider_accessor=None
        )

        visitor = MockVisitor()
        spec.accept(visitor)

        self.assertIsNone(received_accessor[0])


# =============================================================================
# Sociable Tests — тесты с реальными коллабораторами
# =============================================================================

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
