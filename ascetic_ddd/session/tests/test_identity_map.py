import gc
from unittest import TestCase

from ascetic_ddd.session.exceptions import ObjectNotFound
from ascetic_ddd.session.identity_map import IdentityMap
from ascetic_ddd.session.interfaces import IdentityKey


class Model:
    def __init__(self, pk: int):
        self.id = pk


class AnotherModel:
    def __init__(self, pk: int):
        self.id = pk


class IdentityMapTestCase(TestCase):
    def test_get(self):
        identity_map = IdentityMap()
        pk = 3
        obj = Model(pk)
        key = IdentityKey(Model, pk)
        identity_map.add(key, obj)
        result = identity_map.get(key)
        self.assertIs(obj, result)
        with self.assertRaises(KeyError):
            identity_map.get(IdentityKey(Model, 10))

    # noinspection SpellCheckingInspection
    def test_get_weakref_cache(self):
        identity_map = IdentityMap(10)
        pk = 3
        obj = Model(pk)
        obj_id = id(obj)
        key = IdentityKey(Model, pk)
        identity_map.add(key, obj)
        del obj
        gc.collect()
        result = identity_map.get(key)
        self.assertEqual(obj_id, id(result))

    # noinspection SpellCheckingInspection
    def test_get_weakref_cache_crowded(self):
        identity_map = IdentityMap(1)
        pk = 3
        obj = Model(pk)
        key = IdentityKey(Model, pk)
        identity_map.add(key, obj)
        del obj
        identity_map.add(IdentityKey(Model, 10), Model(10))
        gc.collect()
        with self.assertRaises(KeyError):
            identity_map.get(key)

    def test_has(self):
        identity_map = IdentityMap()
        pk = 3
        obj = Model(pk)
        key = IdentityKey(Model, pk)
        identity_map.add(key, obj)
        self.assertTrue(identity_map.has(key))
        self.assertFalse(identity_map.has(IdentityKey(Model, 10)))

    def test_remove(self):
        identity_map = IdentityMap()
        pk = 3
        obj = Model(pk)
        key = IdentityKey(Model, pk)
        identity_map.add(key, obj)
        identity_map.remove(key)
        with self.assertRaises(KeyError):
            identity_map.get(key)

    def test_clear(self):
        identity_map = IdentityMap()
        pk = 3
        obj = Model(pk)
        key = IdentityKey(Model, pk)
        identity_map.add(key, obj)
        identity_map.clear()
        with self.assertRaises(KeyError):
            identity_map.get(key)

    def test_different_entity_types_same_id(self):
        identity_map = IdentityMap()
        pk = 1
        model = Model(pk)
        another = AnotherModel(pk)
        model_key = IdentityKey(Model, pk)
        another_key = IdentityKey(AnotherModel, pk)
        identity_map.add(model_key, model)
        identity_map.add(another_key, another)
        self.assertIs(model, identity_map.get(model_key))
        self.assertIs(another, identity_map.get(another_key))


class SerializableTestCase(TestCase):
    def test_get_nonexistent_object(self):
        identity_map = IdentityMap(isolation_level=IdentityMap.SERIALIZABLE)
        key = IdentityKey(Model, 1)
        identity_map.add(key)
        with self.assertRaises(ObjectNotFound):
            identity_map.get(key)

    def test_has_nonexistent_object(self):
        identity_map = IdentityMap(isolation_level=IdentityMap.SERIALIZABLE)
        key = IdentityKey(Model, 1)
        identity_map.add(key)
        self.assertTrue(identity_map.has(key))

    def test_has_unloaded(self):
        identity_map = IdentityMap(isolation_level=IdentityMap.SERIALIZABLE)
        self.assertFalse(identity_map.has(IdentityKey(Model, 1)))


class RepeatableReadsTestCase(TestCase):
    def test_get(self):
        identity_map = IdentityMap(isolation_level=IdentityMap.REPEATABLE_READS)
        obj = Model(1)
        key = IdentityKey(Model, 1)
        identity_map.add(key, obj)
        self.assertIs(obj, identity_map.get(key))

    def test_add_none_is_noop(self):
        identity_map = IdentityMap(isolation_level=IdentityMap.REPEATABLE_READS)
        key = IdentityKey(Model, 1)
        identity_map.add(key)
        with self.assertRaises(KeyError):
            identity_map.get(key)

    def test_has(self):
        identity_map = IdentityMap(isolation_level=IdentityMap.REPEATABLE_READS)
        key = IdentityKey(Model, 1)
        self.assertFalse(identity_map.has(key))
        identity_map.add(key, Model(1))
        self.assertTrue(identity_map.has(key))


class ReadUncommittedTestCase(TestCase):
    def test_map_disabled(self):
        identity_map = IdentityMap(isolation_level=IdentityMap.READ_UNCOMMITTED)
        obj = Model(1)
        key = IdentityKey(Model, 1)
        identity_map.add(key, obj)
        with self.assertRaises(KeyError):
            identity_map.get(key)
        self.assertFalse(identity_map.has(key))
