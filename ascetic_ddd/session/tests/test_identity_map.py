import gc
from unittest import TestCase

from ascetic_ddd.session.identity_map import IdentityMap
from ascetic_ddd.session.interfaces import IdentityKey


class Model:
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
