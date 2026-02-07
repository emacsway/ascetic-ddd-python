"""Tests for query operator __add__ (merge) and normalize_query."""
import unittest

from ascetic_ddd.faker.domain.query.parser import normalize_query
from ascetic_ddd.faker.domain.query.operators import (
    MergeConflict, EqOperator, RelOperator, CompositeQuery
)


class TestEqOperatorAdd(unittest.TestCase):
    """Tests for EqOperator.__add__."""

    def test_add_same_value(self):
        left = EqOperator(5)
        right = EqOperator(5)
        result = left + right
        self.assertIsInstance(result, EqOperator)
        self.assertEqual(result.value, 5)

    def test_add_different_value_raises(self):
        left = EqOperator(5)
        right = EqOperator(10)
        with self.assertRaises(MergeConflict) as cm:
            left + right

        self.assertEqual(cm.exception.existing_value, 5)
        self.assertEqual(cm.exception.new_value, 10)

    def test_add_none_values(self):
        left = EqOperator(None)
        right = EqOperator(None)
        result = left + right
        self.assertIsInstance(result, EqOperator)
        self.assertIsNone(result.value)

    def test_add_composite_values(self):
        """CompositeQuery (normalized composite PK) merges with itself."""
        inner = CompositeQuery({'tenant': EqOperator(1), 'local': EqOperator(2)})
        result = inner + inner
        self.assertEqual(result, inner)

    def test_add_wrong_type_returns_not_implemented(self):
        result = EqOperator(5).__add__(RelOperator(CompositeQuery({'a': EqOperator(1)})))
        self.assertIs(result, NotImplemented)


class TestRelOperatorAdd(unittest.TestCase):
    """Tests for RelOperator.__add__."""

    def test_add_different_fields(self):
        left = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        right = RelOperator(CompositeQuery({'type': EqOperator('premium')}))
        result = left + right

        self.assertIsInstance(result, RelOperator)
        self.assertEqual(len(result.query.fields), 2)
        self.assertEqual(result.query.fields['status'].value, 'active')
        self.assertEqual(result.query.fields['type'].value, 'premium')

    def test_add_same_field_same_value(self):
        left = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        right = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        result = left + right

        self.assertIsInstance(result, RelOperator)
        self.assertEqual(result.query.fields['status'].value, 'active')

    def test_add_same_field_different_value_raises(self):
        left = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        right = RelOperator(CompositeQuery({'status': EqOperator('inactive')}))

        with self.assertRaises(MergeConflict):
            left + right

    def test_add_nested(self):
        """Deep merge nested RelOperators."""
        left = RelOperator(CompositeQuery({
            'department': RelOperator(CompositeQuery({'name': EqOperator('IT')}))
        }))
        right = RelOperator(CompositeQuery({
            'department': RelOperator(CompositeQuery({'code': EqOperator('IT001')}))
        }))
        result = left + right

        self.assertIsInstance(result, RelOperator)
        dept = result.query.fields['department']
        self.assertIsInstance(dept, RelOperator)
        self.assertEqual(dept.query.fields['name'].value, 'IT')
        self.assertEqual(dept.query.fields['code'].value, 'IT001')

    def test_add_wrong_type_returns_not_implemented(self):
        result = RelOperator(CompositeQuery({'a': EqOperator(1)})).__add__(EqOperator(5))
        self.assertIs(result, NotImplemented)


class TestCompositeQueryAdd(unittest.TestCase):
    """Tests for CompositeQuery.__add__."""

    def test_add_different_fields(self):
        left = CompositeQuery({'a': EqOperator(1)})
        right = CompositeQuery({'b': EqOperator(2)})
        result = left + right

        self.assertIsInstance(result, CompositeQuery)
        self.assertEqual(result.fields['a'].value, 1)
        self.assertEqual(result.fields['b'].value, 2)

    def test_add_same_field_same_value(self):
        left = CompositeQuery({'a': EqOperator(1)})
        right = CompositeQuery({'a': EqOperator(1)})
        result = left + right

        self.assertIsInstance(result, CompositeQuery)
        self.assertEqual(result.fields['a'].value, 1)

    def test_add_same_field_different_value_raises(self):
        left = CompositeQuery({'a': EqOperator(1)})
        right = CompositeQuery({'a': EqOperator(2)})

        with self.assertRaises(MergeConflict):
            left + right

    def test_add_nested(self):
        """Deep merge nested CompositeQueries."""
        left = CompositeQuery({
            'address': CompositeQuery({'city': EqOperator('Moscow')})
        })
        right = CompositeQuery({
            'address': CompositeQuery({'country': EqOperator('Russia')})
        })
        result = left + right

        self.assertIsInstance(result, CompositeQuery)
        addr = result.fields['address']
        self.assertIsInstance(addr, CompositeQuery)
        self.assertEqual(addr.fields['city'].value, 'Moscow')
        self.assertEqual(addr.fields['country'].value, 'Russia')

    def test_add_wrong_type_returns_not_implemented(self):
        result = CompositeQuery({'a': EqOperator(1)}).__add__(EqOperator(5))
        self.assertIs(result, NotImplemented)


class TestCrossTypeAdd(unittest.TestCase):
    """Tests for cross-type __add__ raises TypeError."""

    def test_eq_plus_rel_raises(self):
        with self.assertRaises(TypeError):
            EqOperator(5) + RelOperator(CompositeQuery({'a': EqOperator(1)}))

    def test_composite_plus_eq_raises(self):
        with self.assertRaises(TypeError):
            CompositeQuery({'a': EqOperator(1)}) + EqOperator(5)

    def test_composite_plus_rel_raises(self):
        with self.assertRaises(TypeError):
            CompositeQuery({'a': EqOperator(1)}) + RelOperator(CompositeQuery({'b': EqOperator(2)}))


class TestNormalizeQuery(unittest.TestCase):
    """Tests for normalize_query function."""

    def test_normalize_primitive_eq_unchanged(self):
        """Primitive EqOperator stays unchanged."""
        op = EqOperator(5)
        result = normalize_query(op)
        self.assertIsInstance(result, EqOperator)
        self.assertEqual(result.value, 5)

    def test_normalize_eq_wrapping_composite(self):
        """EqOperator(CompositeQuery(...)) -> CompositeQuery(...)"""
        inner = CompositeQuery({'a': EqOperator(1)})
        op = EqOperator(inner)
        result = normalize_query(op)

        self.assertIsInstance(result, CompositeQuery)
        self.assertIn('a', result.fields)
        self.assertIsInstance(result.fields['a'], EqOperator)
        self.assertEqual(result.fields['a'].value, 1)

    def test_normalize_eq_wrapping_nested_composite(self):
        """EqOperator(CompositeQuery({'a': CompositeQuery(...)})) unwraps outer $eq."""
        inner = CompositeQuery({'b': EqOperator(2)})
        op = EqOperator(CompositeQuery({'a': inner}))
        result = normalize_query(op)

        self.assertIsInstance(result, CompositeQuery)
        self.assertIsInstance(result.fields['a'], CompositeQuery)
        self.assertEqual(result.fields['a'].fields['b'].value, 2)

    def test_normalize_double_wrapped_eq(self):
        """EqOperator(EqOperator(5)) -> EqOperator(5)"""
        op = EqOperator(EqOperator(5))
        result = normalize_query(op)

        self.assertIsInstance(result, EqOperator)
        self.assertEqual(result.value, 5)

    def test_normalize_rel_with_nested_eq_wrapping_composite(self):
        """RelOperator normalizes EqOperator(CompositeQuery) in constraints."""
        inner = CompositeQuery({'x': EqOperator(1), 'y': EqOperator(2)})
        op = RelOperator(CompositeQuery({'a': EqOperator(inner)}))
        result = normalize_query(op)

        self.assertIsInstance(result, RelOperator)
        a = result.query.fields['a']
        self.assertIsInstance(a, CompositeQuery)
        self.assertEqual(a.fields['x'].value, 1)
        self.assertEqual(a.fields['y'].value, 2)

    def test_normalize_composite_with_nested_eq_wrapping_composite(self):
        """CompositeQuery normalizes EqOperator(CompositeQuery) in fields."""
        inner = CompositeQuery({'nested': EqOperator('value')})
        op = CompositeQuery({'a': EqOperator(inner)})
        result = normalize_query(op)

        self.assertIsInstance(result, CompositeQuery)
        a = result.fields['a']
        self.assertIsInstance(a, CompositeQuery)
        self.assertEqual(a.fields['nested'].value, 'value')


if __name__ == '__main__':
    unittest.main()
