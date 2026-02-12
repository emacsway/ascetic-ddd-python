import dataclasses
import typing
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.faker.domain.distributors.m2o.cursor import Cursor
from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.faker.domain.providers.aggregate_provider import AggregateProvider, IAggregateRepository
from ascetic_ddd.faker.domain.providers.provider_change_manager import ProviderChangeManager
from ascetic_ddd.faker.domain.providers.reference_provider import ReferenceProvider
from ascetic_ddd.faker.domain.providers.value_provider import ValueProvider
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification


# =============================================================================
# Value Objects
# =============================================================================

@dataclasses.dataclass(frozen=True)
class TenantId:
    value: int


@dataclasses.dataclass
class Tenant:
    id: TenantId
    name: str


@dataclasses.dataclass(frozen=True)
class AuthorId:
    value: int


@dataclasses.dataclass
class Author:
    id: AuthorId
    tenant_id: TenantId
    name: str


@dataclasses.dataclass(frozen=True)
class PublisherId:
    value: int


@dataclasses.dataclass
class Publisher:
    id: PublisherId
    tenant_id: TenantId
    title: str


@dataclasses.dataclass(frozen=True)
class BookId:
    value: int


@dataclasses.dataclass
class Book:
    id: BookId
    author_id: AuthorId
    publisher_id: PublisherId
    title: str


# =============================================================================
# Stub Infrastructure
# =============================================================================

class StubDistributor(IM2ODistributor):
    def __init__(self, values=None, raise_cursor_at=None):
        self._values = values or []
        self._index = 0
        self._raise_cursor_at = raise_cursor_at
        self._provider_name = None

    async def next(self, session, specification=None):
        if self._raise_cursor_at is not None and self._index >= self._raise_cursor_at:
            raise Cursor(position=self._index, callback=self._append)
        if self._index < len(self._values):
            value = self._values[self._index]
            self._index += 1
            return value
        raise Cursor(position=self._index, callback=self._append)

    async def _append(self, session, value, position=None):
        self._values.append(value)

    async def append(self, session, value):
        await self._append(session, value, None)

    @property
    def provider_name(self):
        return self._provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._provider_name = value

    async def setup(self, session):
        pass

    async def cleanup(self, session):
        pass

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self

    def attach(self, aspect, observer, id_=None):
        pass

    def detach(self, aspect, observer, id_=None):
        pass

    def notify(self, aspect, *args, **kwargs):
        pass

    async def anotify(self, aspect, *args, **kwargs):
        pass

    def bind_external_source(self, external_source):
        pass


class StubRepository:

    def __init__(self, auto_increment_start=1):
        self._storage = {}
        self._counter = auto_increment_start
        self._inserted = []

    def attach(self, aspect, observer, id_=None):
        pass

    def detach(self, aspect, observer, id_=None):
        pass

    def notify(self, aspect, *args, **kwargs):
        pass

    async def anotify(self, aspect, *args, **kwargs):
        pass

    async def find(self, session, specification):
        return list(self._storage.values())

    async def update(self, session, agg):
        pass

    async def setup(self, session):
        pass

    async def cleanup(self, session):
        pass


class StubTenantRepository(StubRepository, IAggregateRepository[Tenant]):

    async def insert(self, session, agg):
        if agg.id is None or (isinstance(agg.id, TenantId) and agg.id.value in (0, None)):
            agg.id = TenantId(value=self._counter)
            self._counter += 1
        self._storage[agg.id.value] = agg
        self._inserted.append(agg)

    async def get(self, session, id_):
        if isinstance(id_, TenantId):
            return self._storage.get(id_.value)
        return None


class StubAuthorRepository(StubRepository, IAggregateRepository[Author]):

    async def insert(self, session, agg):
        if agg.id is None or (isinstance(agg.id, AuthorId) and agg.id.value in (0, None)):
            agg.id = AuthorId(value=self._counter)
            self._counter += 1
        self._storage[agg.id.value] = agg
        self._inserted.append(agg)

    async def get(self, session, id_):
        if isinstance(id_, AuthorId):
            return self._storage.get(id_.value)
        return None


class StubPublisherRepository(StubRepository, IAggregateRepository[Publisher]):

    async def insert(self, session, agg):
        if agg.id is None or (isinstance(agg.id, PublisherId) and agg.id.value in (0, None)):
            agg.id = PublisherId(value=self._counter)
            self._counter += 1
        self._storage[agg.id.value] = agg
        self._inserted.append(agg)

    async def get(self, session, id_):
        if isinstance(id_, PublisherId):
            return self._storage.get(id_.value)
        return None


class StubBookRepository(StubRepository, IAggregateRepository[Book]):

    async def insert(self, session, agg):
        if agg.id is None or (isinstance(agg.id, BookId) and agg.id.value in (0, None)):
            agg.id = BookId(value=self._counter)
            self._counter += 1
        self._storage[agg.id.value] = agg
        self._inserted.append(agg)

    async def get(self, session, id_):
        if isinstance(id_, BookId):
            return self._storage.get(id_.value)
        return None


class MockSession:
    pass


# =============================================================================
# Value Generators
# =============================================================================

async def tenant_id_gen(session, query=None, position=None):
    return (position if position is not None else 0) + 100


async def tenant_name_gen(session, query=None, position=None):
    return "Tenant_%d" % (position if position is not None else 0)


async def author_id_gen(session, query=None, position=None):
    return (position if position is not None else 0) + 200


async def author_name_gen(session, query=None, position=None):
    return "Author_%d" % (position if position is not None else 0)


async def publisher_id_gen(session, query=None, position=None):
    return (position if position is not None else 0) + 300


async def publisher_title_gen(session, query=None, position=None):
    return "Publisher_%d" % (position if position is not None else 0)


async def book_id_gen(session, query=None, position=None):
    return (position if position is not None else 0) + 400


async def book_title_gen(session, query=None, position=None):
    return "Book_%d" % (position if position is not None else 0)


# =============================================================================
# Providers
# =============================================================================

class TenantProvider(AggregateProvider[dict, Tenant]):
    _id_attr = 'id'

    id: ValueProvider[int, TenantId]
    name: ValueProvider[str, str]

    def __init__(self, repository):
        self.id = ValueProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            input_generator=None,  # auto-increment
            output_factory=TenantId,
            output_exporter=lambda x: x.value,
        )
        self.name = ValueProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            input_generator=tenant_name_gen,
        )
        super().__init__(repository=repository, output_factory=Tenant,
                         output_exporter=self._export)

    @staticmethod
    def _export(t):
        return {'id': t.id.value, 'name': t.name}


class AuthorProvider(AggregateProvider[dict, Author]):
    _id_attr = 'id'

    id: ValueProvider[int, AuthorId]
    tenant_id: ReferenceProvider
    name: ValueProvider[str, str]

    def __init__(self, repository, tenant_provider):
        self.id = ValueProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            input_generator=None,
            output_factory=AuthorId,
            output_exporter=lambda x: x.value,
        )
        self.tenant_id = ReferenceProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            aggregate_provider=tenant_provider,
        )
        self.name = ValueProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            input_generator=author_name_gen,
        )
        super().__init__(repository=repository, output_factory=Author,
                         output_exporter=self._export)

    @staticmethod
    def _export(a):
        return {'id': a.id.value, 'tenant_id': a.tenant_id.value, 'name': a.name}


class PublisherProvider(AggregateProvider[dict, Publisher]):
    _id_attr = 'id'

    id: ValueProvider[int, PublisherId]
    tenant_id: ReferenceProvider
    title: ValueProvider[str, str]

    def __init__(self, repository, tenant_provider):
        self.id = ValueProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            input_generator=None,
            output_factory=PublisherId,
            output_exporter=lambda x: x.value,
        )
        self.tenant_id = ReferenceProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            aggregate_provider=tenant_provider,
        )
        self.title = ValueProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            input_generator=publisher_title_gen,
        )
        super().__init__(repository=repository, output_factory=Publisher,
                         output_exporter=self._export)

    @staticmethod
    def _export(p):
        return {'id': p.id.value, 'tenant_id': p.tenant_id.value, 'title': p.title}


class BookProvider(AggregateProvider[dict, Book]):
    """
    Diamond topology:

        [Book]
        /    \\
    [Author] [Publisher]
        \\    /
        [Tenant]
    """
    _id_attr = 'id'

    id: ValueProvider[int, BookId]
    author_id: ReferenceProvider
    publisher_id: ReferenceProvider
    title: ValueProvider[str, str]

    def __init__(self, repository, author_provider, publisher_provider):
        self.id = ValueProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            input_generator=None,
            output_factory=BookId,
            output_exporter=lambda x: x.value,
        )
        self.author_id = ReferenceProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            aggregate_provider=author_provider,
        )
        self.publisher_id = ReferenceProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            aggregate_provider=publisher_provider,
        )
        self.title = ValueProvider(
            distributor=StubDistributor(raise_cursor_at=0),
            input_generator=book_title_gen,
        )
        super().__init__(repository=repository, output_factory=Book,
                         output_exporter=self._export)

    @staticmethod
    def _export(b):
        return {
            'id': b.id.value,
            'author_id': b.author_id.value,
            'publisher_id': b.publisher_id.value,
            'title': b.title,
        }


# =============================================================================
# Tests
# =============================================================================

class ProviderChangeManagerDiamondTestCase(IsolatedAsyncioTestCase):
    """
    Diamond topology: Book -> Author -> Tenant, Book -> Publisher -> Tenant.

    TenantProvider is the SAME instance reachable via two paths.
    ProviderChangeManager must populate Tenant before Author and Publisher,
    and Author/Publisher before Book.
    """

    def setUp(self):
        self.tenant_repo = StubTenantRepository(auto_increment_start=1)
        self.author_repo = StubAuthorRepository(auto_increment_start=1)
        self.publisher_repo = StubPublisherRepository(auto_increment_start=1)
        self.book_repo = StubBookRepository(auto_increment_start=1)
        self.session = MockSession()

        self.tenant_provider = TenantProvider(self.tenant_repo)
        self.tenant_provider.provider_name = 'tenant'

        self.author_provider = AuthorProvider(self.author_repo, self.tenant_provider)
        self.author_provider.provider_name = 'author'

        self.publisher_provider = PublisherProvider(self.publisher_repo, self.tenant_provider)
        self.publisher_provider.provider_name = 'publisher'

        self.book_provider = BookProvider(
            self.book_repo, self.author_provider, self.publisher_provider
        )
        self.book_provider.provider_name = 'book'

    async def test_all_aggregates_created(self):
        """All aggregates in the diamond should be created."""
        cm = ProviderChangeManager()
        await cm.populate(self.session, self.book_provider)

        book = await self.book_provider.create(self.session)

        self.assertIsInstance(book, Book)
        self.assertEqual(len(self.tenant_repo._inserted), 1)
        self.assertEqual(len(self.author_repo._inserted), 1)
        self.assertEqual(len(self.publisher_repo._inserted), 1)
        self.assertEqual(len(self.book_repo._inserted), 1)

    async def test_tenant_populated_exactly_once(self):
        """Tenant (diamond bottom) should be populated exactly once."""
        cm = ProviderChangeManager()
        await cm.populate(self.session, self.book_provider)

        # Tenant was inserted exactly once
        self.assertEqual(len(self.tenant_repo._inserted), 1)

        # Both Author and Publisher reference the same Tenant
        author = await self.author_provider.create(self.session)
        publisher = await self.publisher_provider.create(self.session)
        self.assertEqual(author.tenant_id, publisher.tenant_id)

    async def test_topological_order(self):
        """Tenant before Author/Publisher, Author/Publisher before Book."""
        cm = ProviderChangeManager()
        visited = {}
        edges = []
        cm._collect_providers(self.book_provider, visited, edges)
        sorted_ = cm._topo_sort(visited, edges)
        names = [p.provider_name for p in sorted_]

        # Tenant must come before Author and Publisher
        self.assertLess(names.index('tenant'), names.index('author'))
        self.assertLess(names.index('tenant'), names.index('publisher'))
        # Author and Publisher must come before Book
        self.assertLess(names.index('author'), names.index('book'))
        self.assertLess(names.index('publisher'), names.index('book'))


class ProviderChangeManagerLinearChainTestCase(IsolatedAsyncioTestCase):
    """Linear chain: Author -> Tenant. No diamond."""

    async def test_linear_chain(self):
        tenant_repo = StubTenantRepository(auto_increment_start=1)
        author_repo = StubAuthorRepository(auto_increment_start=1)
        session = MockSession()

        tenant_provider = TenantProvider(tenant_repo)
        tenant_provider.provider_name = 'tenant'

        author_provider = AuthorProvider(author_repo, tenant_provider)
        author_provider.provider_name = 'author'

        cm = ProviderChangeManager()
        await cm.populate(session, author_provider)

        author = await author_provider.create(session)

        self.assertIsInstance(author, Author)
        self.assertEqual(len(tenant_repo._inserted), 1)
        self.assertEqual(len(author_repo._inserted), 1)


class ProviderChangeManagerSingleProviderTestCase(IsolatedAsyncioTestCase):
    """Single provider with no references."""

    async def test_single_provider(self):
        tenant_repo = StubTenantRepository(auto_increment_start=1)
        session = MockSession()

        tenant_provider = TenantProvider(tenant_repo)
        tenant_provider.provider_name = 'tenant'

        cm = ProviderChangeManager()
        await cm.populate(session, tenant_provider)

        tenant = await tenant_provider.create(session)

        self.assertIsInstance(tenant, Tenant)
        self.assertEqual(len(tenant_repo._inserted), 1)


class ProviderChangeManagerCollectProvidersTestCase(IsolatedAsyncioTestCase):
    """Test that _collect_providers finds all AggregateProviders in the graph."""

    def test_diamond_collects_all_four_providers(self):
        tenant_repo = StubTenantRepository()
        author_repo = StubAuthorRepository()
        publisher_repo = StubPublisherRepository()
        book_repo = StubBookRepository()

        tenant_provider = TenantProvider(tenant_repo)
        author_provider = AuthorProvider(author_repo, tenant_provider)
        publisher_provider = PublisherProvider(publisher_repo, tenant_provider)
        book_provider = BookProvider(book_repo, author_provider, publisher_provider)

        cm = ProviderChangeManager()
        visited = {}
        edges = []
        cm._collect_providers(book_provider, visited, edges)

        self.assertEqual(len(visited), 4)

    def test_diamond_has_correct_edges(self):
        tenant_repo = StubTenantRepository()
        author_repo = StubAuthorRepository()
        publisher_repo = StubPublisherRepository()
        book_repo = StubBookRepository()

        tenant_provider = TenantProvider(tenant_repo)
        author_provider = AuthorProvider(author_repo, tenant_provider)
        publisher_provider = PublisherProvider(publisher_repo, tenant_provider)
        book_provider = BookProvider(book_repo, author_provider, publisher_provider)

        cm = ProviderChangeManager()
        visited = {}
        edges = []
        cm._collect_providers(book_provider, visited, edges)

        # Edges: (dependency, dependent)
        # book -> author, book -> publisher, author -> tenant, publisher -> tenant
        edge_set = set(edges)
        self.assertIn((id(author_provider), id(book_provider)), edge_set)
        self.assertIn((id(publisher_provider), id(book_provider)), edge_set)
        self.assertIn((id(tenant_provider), id(author_provider)), edge_set)
        self.assertIn((id(tenant_provider), id(publisher_provider)), edge_set)
        self.assertEqual(len(edges), 4)

    def test_single_provider_no_edges(self):
        tenant_repo = StubTenantRepository()
        tenant_provider = TenantProvider(tenant_repo)

        cm = ProviderChangeManager()
        visited = {}
        edges = []
        cm._collect_providers(tenant_provider, visited, edges)

        self.assertEqual(len(visited), 1)
        self.assertEqual(len(edges), 0)


class ProviderChangeManagerTopoSortTestCase(IsolatedAsyncioTestCase):
    """Test topological sort produces valid ordering."""

    def test_diamond_topo_sort(self):
        tenant_repo = StubTenantRepository()
        author_repo = StubAuthorRepository()
        publisher_repo = StubPublisherRepository()
        book_repo = StubBookRepository()

        tenant_provider = TenantProvider(tenant_repo)
        author_provider = AuthorProvider(author_repo, tenant_provider)
        publisher_provider = PublisherProvider(publisher_repo, tenant_provider)
        book_provider = BookProvider(book_repo, author_provider, publisher_provider)

        cm = ProviderChangeManager()
        visited = {}
        edges = []
        cm._collect_providers(book_provider, visited, edges)
        sorted_ = cm._topo_sort(visited, edges)

        names = [p.provider_name for p in sorted_]
        # None names for providers without provider_name set - assign for test
        tenant_provider.provider_name = 'tenant'
        author_provider.provider_name = 'author'
        publisher_provider.provider_name = 'publisher'
        book_provider.provider_name = 'book'

        # Re-run with names set
        visited2 = {}
        edges2 = []
        cm._collect_providers(book_provider, visited2, edges2)
        sorted2 = cm._topo_sort(visited2, edges2)
        names2 = [p.provider_name for p in sorted2]

        # Tenant must come before Author and Publisher
        self.assertLess(names2.index('tenant'), names2.index('author'))
        self.assertLess(names2.index('tenant'), names2.index('publisher'))
        # Author and Publisher must come before Book
        self.assertLess(names2.index('author'), names2.index('book'))
        self.assertLess(names2.index('publisher'), names2.index('book'))


if __name__ == '__main__':
    import unittest
    unittest.main()
