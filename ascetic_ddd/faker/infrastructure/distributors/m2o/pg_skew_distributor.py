import typing

from ascetic_ddd.faker.domain.distributors.m2o import IM2ODistributor
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.infrastructure.distributors.m2o.pg_weighted_distributor import BasePgDistributor
from ascetic_ddd.faker.infrastructure.specification.pg_specification_visitor import PgSpecificationVisitor


__all__ = ('PgSkewDistributor',)


T = typing.TypeVar("T", covariant=True)


class PgSkewDistributor(BasePgDistributor[T], typing.Generic[T]):
    """
    Distributor with power-law distribution in PostgreSQL.

    A single skew parameter instead of a list of weights:
    - skew = 1.0 -- uniform distribution
    - skew = 2.0 -- moderate skew (first 20% receive ~60% of calls)
    - skew = 3.0 -- strong skew (first 10% receive ~70% of calls)

    Advantages over PgDistributor:
    - A single parameter instead of a list of weights
    - Simpler SQL (no weights table, no cumulative weights)
    - O(1) position selection

    Limitation: when values are created dynamically, earlier values
    receive more calls since they are available longer. Acceptable for a fake data generator.
    """
    _skew: float = 2.0

    def __init__(
            self,
            delegate: IM2ODistributor[T],
            skew: float = 2.0,
            mean: float | None = None,
            initialized: bool = False
    ):
        self._skew = skew
        super().__init__(delegate=delegate, mean=mean, initialized=initialized)

    async def _get_next_value(self, session: ISession, specification: ISpecification[T]) -> tuple[T | None, bool]:
        """
        Value selection with power-law distribution:
        idx = floor(total_values * (1 - random())^skew)

        With skew=1: uniform distribution
        With skew=2: first 50% receive ~75% of calls
        With skew=3: first 33% receive ~70% of calls

        Probabilistic approach for creating new values: with probability 1/mean.
        Works correctly per-specification (WHERE condition is taken into account).
        """
        visitor = PgSpecificationVisitor()
        specification.accept(visitor)

        sql = """
            WITH filtered AS (
                SELECT position, object FROM %(values_table)s %(where)s
            ),
            stats AS (
                SELECT COUNT(*) AS n FROM filtered
            ),
            target AS (
                SELECT
                    -- Power-law distribution: idx = floor(n * (1 - random())^skew)
                    -- skew=1: uniform, skew=2+: skewed toward the beginning
                    LEAST(FLOOR(n * POWER(1 - RANDOM(), %(skew)s))::integer, GREATEST(n - 1, 0)) AS pos,
                    n
                FROM stats
            )
            SELECT
                (SELECT object FROM filtered ORDER BY position OFFSET t.pos LIMIT 1),
                -- Probabilistic approach: create a new value with probability 1/mean
                (t.n = 0 OR RANDOM() < 1.0 / %(expected_mean)s),
                t.n
            FROM target t
        """ % {
            'values_table': self._values_table,
            'where': "WHERE %s" % visitor.sql if visitor.sql else "",
            'skew': self._skew,
            'expected_mean': max(self._mean, 1),
        }

        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(sql, visitor.params)
            row = await acursor.fetchone()
            if not row or not row[0]:
                return (None, True)
            should_create_new = row[1] if row[2] and row[2] > 0 else True
            return (self._deserialize(row[0]), should_create_new)
