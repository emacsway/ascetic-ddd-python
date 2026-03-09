# DDD Application Fake Data Generator

```{index} Faker, Test Data Generation, Load Testing, Index Selectivity, Provider, Distributor
```


```{toctree}
:hidden:

query
```


## Overview

The faker module provides a framework for generating test data with realistic
relationships between {term}`Aggregate` instances.


## Why?

Database index selectivity has a significant impact on load testing results.
The same data volume with different index selectivity can produce substantially different results.

After researching available Open Source solutions, no out-of-the-box solution was found that could reproduce the index selectivity of the target system's database.
Even Claude responded:

> Problems with existing solutions:
> 1. No distribution control — Faker generates uniformly, real data has skew (Zipf, Pareto)
> 2. No M2O/O2M relationships — hard to generate "20% of companies have 80% of orders"
> 3. Stateless — each call is independent, can't reuse created entities
> 4. No specifications — can't request "a company from Moscow with active status"

> But limitations remain:
> 1. Fixed quantity — size=3, not "from 1 to 100 with exponential distribution"
> 2. No reuse — each SubFactory creates a new object, can't "pick an existing company with 80% probability"
> 3. No distribution — can't say "20% of companies get 80% of orders"

Another problem is that generated data must conform to business logic invariants.
Business logic is implemented in the application's domain layer.
Thus, generating valid data implies either fully reproducing the business logic in the fake data generator,
or reusing domain models within the fake data generator.

Since a domain model aggregate is encapsulated, and often requires calling several of its methods
to bring it into the desired state,
while saving an aggregate often involves multiple SQL queries (especially Event Sourced Aggregates),
and external access to the internal state of an encapsulated aggregate is restricted,
the most convenient approach is to reuse domain models within the fake data generator.

An alternative approach involves using the application's CQRS Commands instead of directly accessing the domain model.
CQRS Commands can be invoked either In-Process (bypassing network Hexagonal Adapters)
or Out-Of-Process (through the application's network interface).
In this case, the fake data generator becomes useful not only for generating fake data for load testing,
but also for In-Process Component (Service) Tests, as well as Out-of-Process Component (Service) Tests.
This is typically the level where Acceptance Tests for a Service are written, often using
BDD (Behavior-driven development) and ATDD (Acceptance Test-Driven Development).

For more details on the microservices testing pyramid, see
[Testing Strategies in a Microservice Architecture](https://martinfowler.com/articles/microservice-testing/).

This package can also be used for generating \*csv, \*.jsonl feeds for load testing engines in Command Log format. More details on this will follow.


## Key Concepts

- **Provider**: A component that generates or selects a piece of test data. Providers form a directed acyclic graph.
- **Distributor**: Controls selection strategy (sequence, weighted, random).
- **Reference Provider**: Links aggregates via foreign key relationships.
- **Composite Value Provider**: Generates composite value objects.


## Distribution for distributor

How to extract distribution from an existing project's database?


### Extracting weights for a large range

```sql
SELECT array_agg(weight ORDER BY part)
FROM (
  SELECT
      ntile(4) OVER (ORDER BY c DESC) AS part,
      SUM(c) OVER (PARTITION BY ntile(4) OVER (ORDER BY c DESC)) /
      SUM(c) OVER () AS weight
  FROM (
      SELECT company_id, COUNT(*) AS c
      FROM employees
      WHERE company_id IS NOT NULL
      GROUP BY company_id
  ) AS per_company
) AS t
GROUP BY part;
```


### Extracting skew

Skew is computed via log-log linear regression (Zipf's power law).

Mathematical rationale:
- SkewDistributor uses the formula: `idx = floor(n * (1 - random())^skew)`
- This yields probability density: `p(x) ∝ x^(1/skew - 1)`
- Zipf's law: `freq(rank) ∝ rank^(-alpha)`
- Comparing exponents: `-alpha = 1/skew - 1`

Conversion formulas:
- `alpha = 1 - 1/skew = (skew - 1) / skew`
- `skew = 1 / (1 - alpha)`

```sql
WITH ranked AS (
    SELECT
        company_id,
        COUNT(*) AS freq,
        ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS rank
    FROM employees
    WHERE company_id IS NOT NULL
    GROUP BY company_id
),
log_data AS (
    SELECT
        LN(rank::float) AS log_rank,
        LN(freq::float) AS log_freq
    FROM ranked
    WHERE rank <= (SELECT COUNT(*) * 0.9 FROM ranked)  -- trim the tail
)
SELECT
    1.0 / (1.0 + REGR_SLOPE(log_freq, log_rank)) AS skew,
    -REGR_SLOPE(log_freq, log_rank) AS alpha,
    REGR_R2(log_freq, log_rank) AS r_squared
FROM log_data;
```

Note: `slope < 0` for Zipf data, so `1 + slope = 1 - alpha`.

Interpretation:
- `alpha ≈ 0` → `skew ≈ 1.0` — uniform distribution
- `alpha ≈ 0.5` → `skew ≈ 2.0` — moderate skew
- `alpha ≈ 0.67` → `skew ≈ 3.0` — heavy skew
- `alpha → 1` → `skew → ∞` — extreme skew (everything goes to a single value)
- `r_squared` — goodness of fit (0-1), the closer to 1, the better the data follows the power law


### Extracting weights for a fixed range (choosing from a list)

```sql
SELECT json_agg(val), json_agg(p) FROM (
  SELECT
      status AS val,
      ROUND(COUNT(id)::decimal / SUM(COUNT(id)) OVER (), 5) AS p
  FROM employees
  WHERE status IS NOT NULL
  GROUP BY status
  ORDER BY COUNT(id) DESC
) AS result;
```


### Extracting mean

```sql
SELECT ROUND(COUNT(*)::decimal / GREATEST(COUNT(DISTINCT "company_id"), 1), 5) AS scale
FROM employees
WHERE "company_id" IS NOT NULL;
```


### Extracting null_weight

```sql
SELECT
  CASE WHEN company_id IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS val,
  ROUND(COUNT(id)::decimal / SUM(COUNT(id)) OVER (), 5) AS p
FROM employees
GROUP BY 1
ORDER BY val DESC;
```


## Usage Example

Consider an example with a multi-tenant application: Tenant, Author, and Book.
Book has a composite key (TenantId, InternalBookId).


### Domain Models

```python
import dataclasses

from psycopg_pool import AsyncConnectionPool

from ascetic_ddd.faker.domain.distributors.m2o.factory import distributor_factory
from ascetic_ddd.faker.domain.providers.interfaces import (
    IValueProvider, ICompositeValueProvider, IEntityProvider, IReferenceProvider
)
from ascetic_ddd.faker.domain.providers.aggregate_provider import AggregateProvider
from ascetic_ddd.faker.domain.providers.reference_provider import ReferenceProvider
from ascetic_ddd.faker.domain.providers.composite_value_provider import CompositeValueProvider
from ascetic_ddd.faker.domain.providers.value_provider import ValueProvider
from ascetic_ddd.faker.infrastructure.repositories.composite_repository import CompositeAutoPkRepository
from ascetic_ddd.faker.infrastructure.repositories.internal_pg_repository import InternalPgRepository
from ascetic_ddd.faker.infrastructure.repositories.pg_repository import PgRepository
from ascetic_ddd.faker.infrastructure.session.pg_session import InternalPgSessionPool, ExternalPgSessionPool
from ascetic_ddd.session.composite_session import CompositeSessionPool

from faker import Faker
fake = Faker()

######################## Domain Model ######################################

########### Tenant aggregate #################

@dataclasses.dataclass()
class TenantId:
    value: int | None


@dataclasses.dataclass()
class TenantName:
    value: str


class Tenant:

    def __init__(self, id: TenantId, name: TenantName):
        self._id = id
        self._name = name

    def export(self, exporter: dict):
        exporter['id'] = self._id.value
        exporter['name'] = self._name.value


########### Author Aggregate #################


@dataclasses.dataclass()
class InternalAuthorId:
    value: int | None


class AuthorId:
    tenant_id: TenantId
    author_id: InternalAuthorId

    @property
    def value(self):
        return {
            'tenant_id': self.tenant_id.value,
            'author_id': self.author_id.value,
        }


@dataclasses.dataclass()
class AuthorName:
    value: str


class Author:

    def __init__(self, id: AuthorId, name: AuthorName):
        self._id = id
        self._name = name

    def export(self, exporter: dict):
        exporter['id'] = self._id.value
        exporter['name'] = self._name.value


########### Book aggregate #################

@dataclasses.dataclass()
class InternalBookId:
    value: int | None


@dataclasses.dataclass(frozen=True, kw_only=True)
class BookId:
    tenant_id: TenantId
    book_id: InternalBookId

    @property
    def value(self):
        return {
            'tenant_id': self.tenant_id.value,
            'book_id': self.book_id.value,
        }


@dataclasses.dataclass()
class BookTitle:
    value: str


class Book:

    def __init__(self, id: BookId, author_id: AuthorId, title: BookTitle):
        self._id = id
        self._author_id = author_id
        self._title = title

    def export(self, exporter: dict):
        exporter['id'] = self._id.value
        exporter['_author_id'] = self._author_id.value
        exporter['title'] = self._title.value


######################## Providers ######################################


class TenantProvider(AggregateProvider[dict, Tenant, int, TenantId]):
    _id_attr = 'id'

    id: IValueProvider[int, TenantId]
    name: IValueProvider[str, TenantName]

    def __init__(self, repository):
        self.id = ValueProvider[int, TenantId](
            distributor=distributor_factory(),  # Receive from DB
            output_factory=TenantId,
            output_exporter=lambda x: x.value,
        )
        self.name = ValueProvider[str, TenantName](
            distributor=distributor_factory(sequence=True),
            output_factory=TenantName,
            input_generator=lambda session, position: "Tenant %s" % position,
        )
        super().__init__(
            repository=repository,
            output_factory=Tenant,
            output_exporter=self._export,
        )

    @staticmethod
    def _export(agg: Tenant) -> dict:
        exporter = dict()
        agg.export(exporter)
        return exporter


class AuthorIdProvider(CompositeValueProvider[dict, TenantId]):
    author_id: IValueProvider[int, AuthorId]
    tenant_id: IReferenceProvider[int, TenantId, dict, Tenant]

    def __init__(self, tenant_provider: TenantProvider):
        self.author_id = ValueProvider[int, AuthorId](
            distributor=distributor_factory(),  # Receive from DB
            output_factory=InternalAuthorId,
            output_exporter=lambda x: x.value,
        )
        # Reference to Tenant with skew=2.0 distribution (skewed towards the beginning)
        # mean=10 means on average 10 authors per tenant
        self.tenant_id = ReferenceProvider[int, TenantId, dict, Tenant](
            distributor=distributor_factory(skew=2.0, mean=10),
            aggregate_provider=tenant_provider
        )

        super().__init__(
            output_factory=AuthorId,
            output_exporter=lambda result: result.value
        )


class AuthorProvider(AggregateProvider[dict, Author, dict, AuthorId]):
    _id_attr = 'id'
    id: ICompositeValueProvider[dict, AuthorId]
    name: IValueProvider[str, AuthorName]

    def __init__(self, repository, tenant_provider: TenantProvider):
        self.id = AuthorIdProvider(tenant_provider=tenant_provider)
        self.name = ValueProvider[str, AuthorName](
            input_generator=lambda session, position: "%s %s" % (fake.first_name(), fake.last_name()),
        )
        super().__init__(
            repository=repository,
            output_factory=Author,
            output_exporter=self._export,
        )

    @staticmethod
    def _export(agg: Author) -> dict:
        exporter = dict()
        agg.export(exporter)
        return exporter


class BookIdProvider(CompositeValueProvider[dict, TenantId]):
    book_id: IValueProvider[int, BookId]
    tenant_id: IReferenceProvider[int, TenantId, dict, Tenant]

    def __init__(self, tenant_provider: TenantProvider):
        self.book_id = ValueProvider[int, BookId](
            distributor=distributor_factory(),  # Receive from DB
            output_factory=InternalBookId,
            output_exporter=lambda x: x.value,
        )
        self.tenant_id = ReferenceProvider[int, TenantId, dict, Tenant](
            distributor=distributor_factory(weights=[0.7, 0.2, 0.07, 0.03], mean=50),
            aggregate_provider=tenant_provider
        )

        super().__init__(
            output_factory=AuthorId,
            output_exporter=lambda result: result.value
        )


class BookProvider(AggregateProvider[dict, Book, dict, BookId]):
    _id_attr = 'id'
    id: BookIdProvider
    author_id: IReferenceProvider[dict, AuthorId, dict, Author]
    title: IValueProvider[str, BookTitle]

    def __init__(self, repository, tenant_provider: TenantProvider, author_provider: AuthorProvider):
        self.id = BookIdProvider(tenant_provider=tenant_provider)
        # Reference to Author with weights distribution (20% of authors write 70% of books)
        # mean=50 means on average 50 books per author
        self.author_id = ReferenceProvider[dict, AuthorId, dict, Author](
            distributor=distributor_factory(weights=[0.7, 0.2, 0.07, 0.03], mean=50),
            aggregate_provider=author_provider,
        )
        self.title = ValueProvider[str, BookTitle](
            distributor=distributor_factory(),
            input_generator=lambda session, position: fake.sentence(nb_words=3).replace('.', ''),
        )
        super().__init__(
            repository=repository,
            output_factory=Book,
            output_exporter=self._export,
        )

    async def do_populate(self, session, specification=None):
        # Take tenant_id from id for consistency
        await self.id.populate(session)
        self.author_id.require({'tenant_id': self.id.tenant_id.state(),})
        await super().do_populate(session)

    @staticmethod
    def _export(agg: Book) -> dict:
        exporter = dict()
        agg.export(exporter)
        return exporter


######################## Usage ######################################


tenant_repository = CompositeAutoPkRepository(
    external_repository=PgRepository(),  # Use real Repository instead
    internal_repository=InternalPgRepository(
        table='tenants',
        agg_exporter=TenantProvider._export
    )
)


author_repository = CompositeAutoPkRepository(
    external_repository=PgRepository(),  # Use real Repository instead
    internal_repository=InternalPgRepository(
        table='authors',
        agg_exporter=AuthorProvider._export
    )
)


book_repository = CompositeAutoPkRepository(
    external_repository=PgRepository(),  # Use real Repository instead
    internal_repository=InternalPgRepository(
        table='books',
        agg_exporter=BookProvider._export
    )
)

# Create providers
tenant_provider = TenantProvider(tenant_repository)
author_provider = AuthorProvider(author_repository, tenant_provider)
book_provider = BookProvider(book_repository, tenant_provider, author_provider)

async def generate_data():

    internal_pg_pool = AsyncConnectionPool('internal_postgresql_url', max_size=4, open=False)
    await internal_pg_pool.open()
    internal_session_pool = InternalPgSessionPool(internal_pg_pool)

    external_pg_pool = AsyncConnectionPool('internal_postgresql_url', max_size=4, open=False)
    await external_pg_pool.open()
    external_session_pool = ExternalPgSessionPool(external_pg_pool)

    session_pool = CompositeSessionPool(external_session_pool, internal_session_pool)

    # Generate 1000 books
    for _ in range(1000):
        with session_pool.session() as session, session.atomic() as ts_session:
            book_provider.reset()
            await book_provider.populate(ts_session)
            book = book_provider.output()
            print(f"Created: {book._title} by {book._author_id}")
```


### Distributor parameters

| Parameter | Description |
|-----------|-------------|
| `weights` | List of partition weights, e.g. `[0.7, 0.2, 0.07, 0.03]` — 70% will fall into the first partition |
| `skew` | Skew parameter: 1.0 = uniform, 2.0+ = skewed towards the beginning |
| `mean` | Average number of uses for each value. `mean=1` for unique values |
| `null_weight` | Probability of returning None (0-1) |
| `sequence` | Pass ordinal number to the value generator |


## API Reference

See the {doc}`/api/index` section for auto-generated API documentation of:

- {mod}`ascetic_ddd.faker.domain.providers.interfaces`
- {mod}`ascetic_ddd.faker.domain.distributors.m2o.interfaces`
- {mod}`ascetic_ddd.faker.domain.query.operators`
- {mod}`ascetic_ddd.faker.domain.specification.interfaces`
