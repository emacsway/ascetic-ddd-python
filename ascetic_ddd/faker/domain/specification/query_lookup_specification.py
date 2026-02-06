"""
Query-based lookup specification.
"""
import typing

from ascetic_ddd.faker.domain.query.operators import IQueryOperator
from ascetic_ddd.faker.domain.query.visitors import query_to_plain_value
from ascetic_ddd.faker.domain.specification.interfaces import ISpecificationVisitor, ISpecification
from ascetic_ddd.seedwork.domain.session import ISession
from ascetic_ddd.seedwork.domain.utils.data import is_subset

__all__ = ('QueryLookupSpecification',)


T = typing.TypeVar("T", covariant=True)


class QueryLookupSpecification(ISpecification[T], typing.Generic[T]):
    """
    Specification с nested lookup в is_satisfied_by().

    В отличие от QueryResolvableSpecification, не резолвит вложенные constraints
    заранее, а делает lookup при каждой проверке (с кешированием).

    Преимущества:
    - Один индекс на логический паттерн (эффективное индексирование)
    - Новые объекты автоматически учитываются (lookup в момент проверки)

    Недостатки:
    - Распределение nested объектов не учитывается
    - Требует доступ к providers при is_satisfied_by()

    Пример:
        query = QueryParser().parse({'fk_id': {'$rel': {'status': {'$eq': 'active'}}}})
        spec = QueryLookupSpecification(
            query,
            lambda obj: {'fk_id': obj.fk_id},
            aggregate_provider_accessor=lambda: aggregate_provider
        )
        # Индекс один для всех объектов с active fk
        # is_satisfied_by() проверяет fk.status == 'active' через lookup
    """

    _query: IQueryOperator
    _hash: int | None
    _str: str | None
    _object_exporter: typing.Callable[[T], dict]
    _aggregate_provider_accessor: typing.Callable[[], typing.Any] | None
    _nested_cache: dict[tuple[type, str, typing.Any], bool]  # {(provider_type, field_key, fk_id): matches}

    __slots__ = (
        '_query',
        '_object_exporter',
        '_hash',
        '_str',
        '_aggregate_provider_accessor',
        '_nested_cache',
    )

    def __init__(
            self,
            query: IQueryOperator,
            object_exporter: typing.Callable[[T], dict],
            aggregate_provider_accessor: typing.Callable[[], typing.Any] | None = None,
    ):
        self._query = query
        self._object_exporter = object_exporter
        self._aggregate_provider_accessor = aggregate_provider_accessor
        self._hash = None
        self._str = None
        self._nested_cache = {}

    def __str__(self) -> str:
        if self._str is None:
            self._str = repr(self._query)
        return self._str

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(self._query)
        return self._hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QueryLookupSpecification):
            return False
        return self._query == other._query

    async def is_satisfied_by(self, session: ISession, obj: T) -> bool:
        object_pattern = query_to_plain_value(self._query)

        if self._aggregate_provider_accessor is None:
            # Без провайдеров - только простое сравнение
            state = self._object_exporter(obj)
            return is_subset(object_pattern, state)

        state = self._object_exporter(obj)
        aggregate_provider = self._aggregate_provider_accessor()
        return await self._matches_pattern_with_provider(
            session, object_pattern, state, aggregate_provider
        )

    async def _matches_pattern_with_provider(
            self,
            session: typing.Any,
            pattern: dict,
            state: dict,
            aggregate_provider: typing.Any
    ) -> bool:
        """Проверяет соответствие state паттерну с nested lookup через провайдер."""
        for key, value in pattern.items():
            if isinstance(value, dict):
                # Nested constraint - нужен lookup
                if not await self._matches_nested(session, key, state.get(key), value, aggregate_provider):
                    return False
            else:
                # Simple value comparison
                if state.get(key) != value:
                    return False
        return True

    async def _matches_nested(
            self,
            session: typing.Any,
            field_key: str,
            fk_id: typing.Any,
            nested_pattern: dict,
            aggregate_provider: typing.Any
    ) -> bool:
        """
        Проверяет, удовлетворяет ли связанный объект nested pattern.

        Использует кеш для избежания повторных lookup'ов.

        Args:
            session: сессия для запросов к repository
            field_key: имя поля (ключ для провайдера)
            fk_id: значение foreign key
            nested_pattern: паттерн для проверки связанного объекта
            aggregate_provider: провайдер текущего уровня

        Returns:
            True если связанный объект удовлетворяет паттерну
        """
        if fk_id is None:
            return False

        # Ключ кеша включает тип провайдера для избежания коллизий
        # между одинаковыми field_key на разных уровнях вложенности
        cache_key = (type(aggregate_provider), field_key, fk_id)

        if cache_key in self._nested_cache:
            return self._nested_cache[cache_key]

        # Делаем lookup
        result = await self._do_nested_lookup(session, field_key, fk_id, nested_pattern, aggregate_provider)
        self._nested_cache[cache_key] = result
        return result

    async def _do_nested_lookup(
            self,
            session: typing.Any,
            field_key: str,
            fk_id: typing.Any,
            nested_pattern: dict,
            aggregate_provider: typing.Any
    ) -> bool:
        """
        Выполняет lookup связанного объекта и проверяет паттерн.

        Args:
            session: сессия для запросов к repository
            field_key: имя поля (ключ для провайдера)
            fk_id: значение foreign key
            nested_pattern: паттерн для проверки
            aggregate_provider: провайдер текущего уровня

        Returns:
            True если связанный объект удовлетворяет паттерну
        """
        from ascetic_ddd.faker.domain.providers.interfaces import IReferenceProvider

        providers = aggregate_provider.providers
        nested_provider = providers.get(field_key)

        if not isinstance(nested_provider, IReferenceProvider):
            # Не reference provider - не можем делать lookup
            return fk_id is not None

        # Получаем связанный объект через repository вложенного агрегата
        referenced_aggregate_provider = nested_provider.aggregate_provider
        repository = referenced_aggregate_provider._repository
        foreign_obj = await repository.get(session, fk_id)

        if foreign_obj is None:
            return False

        # Экспортируем состояние через exporter вложенного агрегата
        foreign_state = referenced_aggregate_provider._output_exporter(foreign_obj)

        # Рекурсивно проверяем nested pattern с провайдером вложенного уровня
        return await self._matches_pattern_with_provider(
            session, nested_pattern, foreign_state, referenced_aggregate_provider
        )

    def accept(self, visitor: ISpecificationVisitor):
        visitor.visit_query_specification(
            self._query,
            self._aggregate_provider_accessor
        )

    def clear_cache(self) -> None:
        """Очищает кеш nested lookup'ов."""
        self._nested_cache.clear()
