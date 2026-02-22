import contextlib
import typing
import weakref

from ascetic_ddd.session.exceptions import ObjectNotFound
from ascetic_ddd.session.interfaces import IdentityKey, IIdentityMap

__all__ = ("IdentityMap",)


class NonexistentObject:
    pass


class CacheLru:
    _order: list[object]

    def __init__(self, size=1000) -> None:
        self._order = []
        self._size = size

    def add(self, value: object) -> None:
        self._order.append(value)
        if len(self._order) > self._size:
            self._order.pop(0)

    def touch(self, value: object) -> None:
        obj = value
        with contextlib.suppress(ValueError, IndexError):
            obj = self._order.pop(self._order.index(obj))
        self._order.append(obj)

    def remove(self, value: object) -> None:
        with contextlib.suppress(IndexError):
            self._order.remove(value)

    def clear(self) -> None:
        del self._order[:]

    def set_size(self, size: int) -> None:
        self._size = size


class IStrategy:
    def add(self, key: IdentityKey, value: object | None = None) -> None:
        raise NotImplementedError

    def get(self, key: IdentityKey) -> object:
        raise NotImplementedError

    def has(self, key: IdentityKey) -> bool:
        raise NotImplementedError


class BaseStrategy(IStrategy):
    _identity_map_ref: weakref.ref["IdentityMap"]

    def __init__(self, identity_map: "IdentityMap") -> None:
        self._identity_map_ref = weakref.ref(identity_map)

    def _identity_map(self) -> "IdentityMap":
        im = self._identity_map_ref()
        assert im is not None
        return im


class ReadUncommittedStrategy(BaseStrategy):
    def add(self, key: IdentityKey, value: object | None = None) -> None:
        pass

    def get(self, key: IdentityKey) -> object:
        raise KeyError

    def has(self, key: IdentityKey) -> bool:
        return False


class ReadCommittedStrategy(ReadUncommittedStrategy):
    pass


class RepeatableReadsStrategy(BaseStrategy):
    def add(self, key: IdentityKey, value: object | None = None) -> None:
        if value is not None:
            self._identity_map().do_add(key, value)

    def get(self, key: IdentityKey) -> object:
        obj = self._identity_map().do_get(key)
        if isinstance(obj, NonexistentObject):
            raise KeyError
        return obj

    def has(self, key: IdentityKey) -> bool:
        try:
            obj = self._identity_map().do_get(key)
        except KeyError:
            return False
        else:
            return not isinstance(obj, NonexistentObject)


class SerializableStrategy(BaseStrategy):
    def add(self, key: IdentityKey, value: object | None = None) -> None:
        if value is None:
            value = NonexistentObject()
        self._identity_map().do_add(key, value)

    def get(self, key: IdentityKey) -> object:
        obj = self._identity_map().do_get(key)
        if isinstance(obj, NonexistentObject):
            raise ObjectNotFound
        return obj

    def has(self, key: IdentityKey) -> bool:
        try:
            self._identity_map().do_get(key)
        except KeyError:
            return False
        else:
            return True


T = typing.TypeVar("T")


class IdentityMap(IIdentityMap):
    _strategy: IStrategy
    _cache: CacheLru
    _alive: weakref.WeakValueDictionary[IdentityKey, object]

    READ_UNCOMMITTED = 0  # IdentityMap is disabled
    READ_COMMITTED = 1  # IdentityMap is disabled
    REPEATABLE_READS = 2  # Prevent repeated DB-query only for existent objects
    SERIALIZABLE = 3  # Prevent repeated DB-query for both, existent and nonexistent objects

    STRATEGY_MAP = {
        READ_UNCOMMITTED: ReadUncommittedStrategy,
        READ_COMMITTED: ReadCommittedStrategy,
        REPEATABLE_READS: RepeatableReadsStrategy,
        SERIALIZABLE: SerializableStrategy,
    }

    def __init__(self, cache_size: int = 100, isolation_level: int = SERIALIZABLE) -> None:
        self._cache = CacheLru(cache_size)
        self._alive = weakref.WeakValueDictionary()
        self.set_isolation_level(isolation_level)

    def add(self, key: IdentityKey[T], value: T | None = None) -> None:
        self._strategy.add(key, value)

    def get(self, key: IdentityKey[T]) -> T:
        return typing.cast(T, self._strategy.get(key))

    def has(self, key: IdentityKey) -> bool:
        return self._strategy.has(key)

    def do_add(self, key: IdentityKey, value: object | None = None) -> None:
        self._cache.add(value)
        self._alive[key] = value

    def do_get(self, key: IdentityKey) -> object:
        value = self._alive[key]
        self._cache.touch(value)
        return value

    def do_has(self, key: IdentityKey) -> bool:
        return key in self._alive

    def remove(self, key: IdentityKey) -> None:
        try:
            obj = self._alive[key]
            self._cache.remove(obj)
            del self._alive[key]
            # self._alive.pop(key)
        except KeyError:
            pass

    def clear(self) -> None:
        self._cache.clear()
        self._alive.clear()

    def set_isolation_level(self, level: int) -> None:
        self._strategy = self.STRATEGY_MAP[level](self)
