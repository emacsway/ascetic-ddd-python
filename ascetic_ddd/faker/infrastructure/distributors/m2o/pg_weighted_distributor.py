import math
import random
import typing
from abc import abstractmethod

from ascetic_ddd.faker.domain.distributors.m2o.interfaces import IM2ODistributor
from ascetic_ddd.faker.infrastructure.distributors.m2o.pg_write_distributor import PgWriteDistributor
from ascetic_ddd.option import Option, Some
from ascetic_ddd.signals.interfaces import IAsyncSignal
from ascetic_ddd.faker.domain.distributors.m2o.events import ValueAppendedEvent
from ascetic_ddd.session.interfaces import ISession
from ascetic_ddd.faker.domain.specification.interfaces import ISpecification
from ascetic_ddd.faker.infrastructure.session.pg_session import extract_internal_connection
from ascetic_ddd.faker.infrastructure.specification.pg_specification_visitor import PgSpecificationVisitor
from ascetic_ddd.utils import serializer


__all__ = ('BasePgDistributor', 'PgWeightedDistributor')


T = typing.TypeVar("T")


class BasePgDistributor(IM2ODistributor[T], typing.Generic[T]):
    """
    Base class for PostgreSQL read distributors.

    Pure read decorator over PgWriteDistributor.
    All write operations (append, setup, cleanup) delegate to store.

    Limitation: when values are created dynamically, earlier values
    receive more calls since they are available longer. Acceptable for a fake data generator.

    Args:
        store: PgWriteDistributor that owns the PG table.
        mean: Average number of usages for each value.
    """
    _extract_connection = staticmethod(extract_internal_connection)
    _mean: float = 50
    _store: PgWriteDistributor[T]

    def __init__(
            self,
            store: PgWriteDistributor[T],
            mean: float | None = None,
    ):
        self._store = store
        if mean is not None:
            self._mean = mean
        super().__init__()

    async def next(
            self,
            session: ISession,
            specification: ISpecification[T],
    ) -> Option[T]:
        await self._store.setup(session)

        value, should_create_new = await self._get_next_value(session, specification)
        if should_create_new:
            return await self._store.next(session, specification)
        assert value is not None
        return Some(value)

    @abstractmethod
    async def _get_next_value(self, session: ISession, specification: ISpecification[T]) -> tuple[T | None, bool]:
        raise NotImplementedError

    async def append(self, session: ISession, value: T):
        await self._store.append(session, value)

    @property
    def provider_name(self):
        return self._store.provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._store.provider_name = value

    @property
    def on_appended(self) -> IAsyncSignal[ValueAppendedEvent[T]]:
        return self._store.on_appended

    async def setup(self, session: ISession):
        await self._store.setup(session)

    async def cleanup(self, session: ISession):
        await self._store.cleanup(session)

    _deserialize = staticmethod(serializer.deserialize)

    def __copy__(self):
        return self

    def __deepcopy__(self, memodict={}):
        return self


# =============================================================================
# PgWeightedDistributor
# =============================================================================

class PgWeightedDistributor(BasePgDistributor[T], typing.Generic[T]):
    """
    Read distributor with weighted distribution in PostgreSQL.

    Limitation: when values are created dynamically, earlier values
    receive more calls since they are available longer. This yields ~85% vs 70% for the first
    partition instead of exact weight matching. Acceptable for a fake data generator.
    """
    _weights: list[float]

    def __init__(
            self,
            store: PgWriteDistributor[T],
            weights: typing.Iterable[float] = tuple(),
            mean: float | None = None,
    ):
        self._weights = list(weights)
        super().__init__(store=store, mean=mean)

    def _compute_partition(self) -> tuple[int, float, int]:
        """
        Computes the partition in Python.

        Returns:
            (partition_idx, local_skew, num_partitions)

        Uses the LEFT partition (LAG) and shifts toward the END -- this compensates for the fact
        that earlier values receive more calls (available longer during dynamic creation).
        For weights=[0.7, 0.2, 0.07, 0.03]:
          partition 0: first -> local_skew=1.0 (uniform)
          partition 1: ratio=3.5 -> local_skew~=2.81 (shift toward end, closer to partition 0)
          partition 2: ratio=2.86 -> local_skew~=2.52
          partition 3: ratio=2.33 -> local_skew~=2.22
        """
        num_partitions = len(self._weights)
        if num_partitions == 0:
            return (0, 1.0, 1)

        # Select partition by weights -- O(w)
        partition_idx = random.choices(range(num_partitions), weights=self._weights, k=1)[0]

        # Compute local skew from the weight ratio of adjacent partitions
        if partition_idx > 0:
            prev_weight = self._weights[partition_idx - 1]
            curr_weight = self._weights[partition_idx]
            if curr_weight > 0:
                ratio = prev_weight / curr_weight
                local_skew = max(1.0, math.log2(ratio) + 1)
            else:
                local_skew = 2.0
        else:
            local_skew = 1.0

        return (partition_idx, local_skew, num_partitions)

    async def _get_next_value(self, session: ISession, specification: ISpecification[T]) -> tuple[T | None, bool]:
        """
        Optimized value selection:
        1. Select partition by weights -- O(w) in Python
        2. Select position within partition with slope bias -- O(1) in SQL
        3. Retrieve value by position -- O(log n) with index
        4. Probabilistic decision on creating a new value
        """
        visitor = PgSpecificationVisitor()
        specification.accept(visitor)

        partition_idx, local_skew, num_partitions = self._compute_partition()

        sql = """
            WITH filtered AS (
                SELECT position, object FROM %(values_table)s %(where)s
            ),
            stats AS (
                SELECT COUNT(*) AS n FROM filtered
            ),
            target AS (
                SELECT
                    -- end = floor((partition_idx + 1) * total / num_partitions)
                    -- size = ceil(total / num_partitions)
                    -- pos = end - 1 - floor(size * (1 - random())^local_skew)
                    -- Shift toward the END of the partition (closer to the previous one)
                    GREATEST(0,
                        FLOOR((%(partition_idx)s + 1) * n::decimal / %(num_partitions)s)::integer - 1 -
                        LEAST(
                            FLOOR(CEIL(n::decimal / %(num_partitions)s) * POWER(1 - RANDOM(), %(local_skew)s))::integer,
                            GREATEST(CEIL(n::decimal / %(num_partitions)s)::integer - 1, 0)
                        )
                    ) AS pos,
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
            'values_table': self._store.values_table,
            'where': "WHERE %s" % visitor.sql if visitor.sql else "",
            'partition_idx': partition_idx,
            'num_partitions': num_partitions,
            'local_skew': local_skew,
            'expected_mean': max(self._mean, 1),
        }

        async with self._extract_connection(session).cursor() as acursor:
            await acursor.execute(sql, visitor.params)
            row = await acursor.fetchone()
            if not row or not row[0]:
                return (None, True)
            should_create_new = row[1] if row[2] and row[2] > 0 else True
            return (self._deserialize(row[0]), should_create_new)
