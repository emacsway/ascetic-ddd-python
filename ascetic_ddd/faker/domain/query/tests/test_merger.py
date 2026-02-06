"""Tests for QueryMerger."""
import unittest

from ascetic_ddd.faker.domain.query.merger import QueryMerger, normalize_query
from ascetic_ddd.faker.domain.query.operators import (
    EqOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.domain.providers.exceptions import DiamondUpdateConflict


class TestQueryMergerBasic(unittest.TestCase):
    """Basic merge tests."""

    def setUp(self):
        self.merger = QueryMerger(id_attr='id')

    def test_merge_none_left(self):
        right = EqOperator(5)
        result = self.merger.merge(None, right, 'test')
        self.assertEqual(result, right)

    def test_merge_none_right(self):
        left = EqOperator(5)
        result = self.merger.merge(left, None, 'test')
        self.assertEqual(result, left)

    def test_merge_both_none(self):
        result = self.merger.merge(None, None, 'test')
        self.assertIsNone(result)


class TestQueryMergerEqOperator(unittest.TestCase):
    """Tests for merging EqOperators."""

    def setUp(self):
        self.merger = QueryMerger(id_attr='id')

    def test_merge_eq_eq_same_value(self):
        left = EqOperator(5)
        right = EqOperator(5)
        result = self.merger.merge(left, right, 'test')
        self.assertIsInstance(result, EqOperator)
        self.assertEqual(result.value, 5)

    def test_merge_eq_eq_different_value_raises(self):
        left = EqOperator(5)
        right = EqOperator(10)
        with self.assertRaises(DiamondUpdateConflict) as cm:
            self.merger.merge(left, right, 'test_provider')

        self.assertEqual(cm.exception.existing_value, 5)
        self.assertEqual(cm.exception.new_value, 10)
        self.assertEqual(cm.exception.provider_name, 'test_provider')

    def test_merge_eq_eq_none_values(self):
        left = EqOperator(None)
        right = EqOperator(None)
        result = self.merger.merge(left, right, 'test')
        self.assertIsInstance(result, EqOperator)
        self.assertIsNone(result.value)

    def test_merge_eq_eq_complex_values(self):
        """EqOperator can contain parsed composite PK."""
        inner = CompositeQuery({'tenant': EqOperator(1), 'local': EqOperator(2)})
        left = EqOperator(inner)
        right = EqOperator(inner)
        result = self.merger.merge(left, right, 'test')
        self.assertEqual(result.value, inner)


class TestQueryMergerRelOperator(unittest.TestCase):
    """Tests for merging RelOperators."""

    def setUp(self):
        self.merger = QueryMerger(id_attr='id')

    def test_merge_rel_rel_different_fields(self):
        left = RelOperator({'status': EqOperator('active')})
        right = RelOperator({'type': EqOperator('premium')})
        result = self.merger.merge(left, right, 'test')

        self.assertIsInstance(result, RelOperator)
        self.assertEqual(len(result.constraints), 2)
        self.assertEqual(result.constraints['status'].value, 'active')
        self.assertEqual(result.constraints['type'].value, 'premium')

    def test_merge_rel_rel_same_field_same_value(self):
        left = RelOperator({'status': EqOperator('active')})
        right = RelOperator({'status': EqOperator('active')})
        result = self.merger.merge(left, right, 'test')

        self.assertIsInstance(result, RelOperator)
        self.assertEqual(result.constraints['status'].value, 'active')

    def test_merge_rel_rel_same_field_different_value_raises(self):
        left = RelOperator({'status': EqOperator('active')})
        right = RelOperator({'status': EqOperator('inactive')})

        with self.assertRaises(DiamondUpdateConflict):
            self.merger.merge(left, right, 'test')

    def test_merge_rel_rel_nested(self):
        """Deep merge nested RelOperators."""
        left = RelOperator({
            'department': RelOperator({'name': EqOperator('IT')})
        })
        right = RelOperator({
            'department': RelOperator({'code': EqOperator('IT001')})
        })
        result = self.merger.merge(left, right, 'test')

        self.assertIsInstance(result, RelOperator)
        dept = result.constraints['department']
        self.assertIsInstance(dept, RelOperator)
        self.assertEqual(dept.constraints['name'].value, 'IT')
        self.assertEqual(dept.constraints['code'].value, 'IT001')


class TestQueryMergerEqRel(unittest.TestCase):
    """Tests for merging EqOperator with RelOperator."""

    def setUp(self):
        self.merger = QueryMerger(id_attr='id')

    def test_merge_eq_into_rel(self):
        eq = EqOperator(27)
        rel = RelOperator({'status': EqOperator('active')})
        result = self.merger.merge(eq, rel, 'test')

        self.assertIsInstance(result, RelOperator)
        self.assertEqual(result.constraints['status'].value, 'active')
        self.assertEqual(result.constraints['id'].value, 27)

    def test_merge_rel_eq(self):
        """Order shouldn't matter."""
        rel = RelOperator({'status': EqOperator('active')})
        eq = EqOperator(27)
        result = self.merger.merge(rel, eq, 'test')

        self.assertIsInstance(result, RelOperator)
        self.assertEqual(result.constraints['status'].value, 'active')
        self.assertEqual(result.constraints['id'].value, 27)

    def test_merge_eq_into_rel_with_existing_id(self):
        """If id already exists in $rel, merge them."""
        eq = EqOperator(27)
        rel = RelOperator({
            'status': EqOperator('active'),
            'id': EqOperator(27)  # same value
        })
        result = self.merger.merge(eq, rel, 'test')

        self.assertIsInstance(result, RelOperator)
        self.assertEqual(result.constraints['id'].value, 27)

    def test_merge_eq_into_rel_with_conflicting_id_raises(self):
        eq = EqOperator(27)
        rel = RelOperator({
            'status': EqOperator('active'),
            'id': EqOperator(99)  # different value
        })

        with self.assertRaises(DiamondUpdateConflict):
            self.merger.merge(eq, rel, 'test')

    def test_merge_with_custom_id_attr(self):
        """Use custom id_attr for composite PKs."""
        merger = QueryMerger(id_attr='pk')
        inner = CompositeQuery({'tenant': EqOperator(1), 'local': EqOperator(2)})
        eq = EqOperator(inner)
        rel = RelOperator({'status': EqOperator('active')})
        result = merger.merge(eq, rel, 'test')

        self.assertIsInstance(result, RelOperator)
        self.assertEqual(result.constraints['pk'].value, inner)


class TestQueryMergerCompositeQuery(unittest.TestCase):
    """Tests for merging CompositeQueries."""

    def setUp(self):
        self.merger = QueryMerger(id_attr='id')

    def test_merge_composite_composite_different_fields(self):
        left = CompositeQuery({'a': EqOperator(1)})
        right = CompositeQuery({'b': EqOperator(2)})
        result = self.merger.merge(left, right, 'test')

        self.assertIsInstance(result, CompositeQuery)
        self.assertEqual(result.fields['a'].value, 1)
        self.assertEqual(result.fields['b'].value, 2)

    def test_merge_composite_composite_same_field_same_value(self):
        left = CompositeQuery({'a': EqOperator(1)})
        right = CompositeQuery({'a': EqOperator(1)})
        result = self.merger.merge(left, right, 'test')

        self.assertIsInstance(result, CompositeQuery)
        self.assertEqual(result.fields['a'].value, 1)

    def test_merge_composite_composite_same_field_different_value_raises(self):
        left = CompositeQuery({'a': EqOperator(1)})
        right = CompositeQuery({'a': EqOperator(2)})

        with self.assertRaises(DiamondUpdateConflict):
            self.merger.merge(left, right, 'test')

    def test_merge_composite_composite_nested(self):
        """Deep merge nested CompositeQueries."""
        left = CompositeQuery({
            'address': CompositeQuery({'city': EqOperator('Moscow')})
        })
        right = CompositeQuery({
            'address': CompositeQuery({'country': EqOperator('Russia')})
        })
        result = self.merger.merge(left, right, 'test')

        self.assertIsInstance(result, CompositeQuery)
        addr = result.fields['address']
        self.assertIsInstance(addr, CompositeQuery)
        self.assertEqual(addr.fields['city'].value, 'Moscow')
        self.assertEqual(addr.fields['country'].value, 'Russia')


class TestQueryMergerIncompatibleTypes(unittest.TestCase):
    """Tests for merging incompatible operator types."""

    def setUp(self):
        self.merger = QueryMerger(id_attr='id')

    def test_merge_composite_eq_keeps_eq(self):
        """EqOperator is more specific than CompositeQuery, keep EqOperator."""
        left = CompositeQuery({'a': EqOperator(1)})
        right = EqOperator(5)

        result = self.merger.merge(left, right, 'test')

        # EqOperator wins as more specific value
        self.assertIsInstance(result, EqOperator)
        self.assertEqual(result.value, 5)

    def test_merge_composite_rel_places_under_id(self):
        """CompositeQuery + RelOperator -> places CompositeQuery under $rel.id."""
        left = CompositeQuery({'a': EqOperator(1)})
        right = RelOperator({'status': EqOperator('active')})

        result = self.merger.merge(left, right, 'test')

        self.assertIsInstance(result, RelOperator)
        self.assertIn('id', result.constraints)
        self.assertIn('status', result.constraints)
        self.assertEqual(result.constraints['id'], left)


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
        op = RelOperator({'a': EqOperator(inner)})
        result = normalize_query(op)

        self.assertIsInstance(result, RelOperator)
        a = result.constraints['a']
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
