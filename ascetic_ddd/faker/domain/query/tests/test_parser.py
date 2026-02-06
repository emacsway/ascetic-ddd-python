"""Tests for QueryParser."""
import unittest

from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.faker.domain.query.operators import (
    EqOperator, RelOperator, CompositeQuery
)


class TestQueryParserScalar(unittest.TestCase):
    """Tests for QueryParser.parse() with scalar values (implicit $eq)."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_scalar_int(self):
        result = self.parser.parse(5)
        self.assertIsInstance(result, EqOperator)
        self.assertEqual(result.value, 5)

    def test_parse_scalar_string(self):
        result = self.parser.parse("hello")
        self.assertIsInstance(result, EqOperator)
        self.assertEqual(result.value, "hello")

    def test_parse_scalar_none(self):
        result = self.parser.parse(None)
        self.assertIsInstance(result, EqOperator)
        self.assertIsNone(result.value)

    def test_parse_scalar_bool(self):
        result = self.parser.parse(True)
        self.assertIsInstance(result, EqOperator)
        self.assertIs(result.value, True)


class TestQueryParserExplicitEq(unittest.TestCase):
    """Tests for QueryParser.parse() with explicit $eq."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_eq_operator(self):
        result = self.parser.parse({'$eq': 42})
        self.assertIsInstance(result, EqOperator)
        self.assertEqual(result.value, 42)

    def test_parse_eq_operator_with_none(self):
        result = self.parser.parse({'$eq': None})
        self.assertIsInstance(result, EqOperator)
        self.assertIsNone(result.value)

    def test_parse_eq_operator_with_dict(self):
        """$eq can contain composite value (dict)."""
        result = self.parser.parse({'$eq': {'tenant_id': 1, 'local_id': 2}})
        self.assertIsInstance(result, EqOperator)
        self.assertEqual(result.value, {'tenant_id': 1, 'local_id': 2})


class TestQueryParserRel(unittest.TestCase):
    """Tests for QueryParser.parse() with $rel operator."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_rel_operator_simple(self):
        result = self.parser.parse({'$rel': {'status': {'$eq': 'active'}}})
        self.assertIsInstance(result, RelOperator)
        self.assertIn('status', result.constraints)
        self.assertIsInstance(result.constraints['status'], EqOperator)
        self.assertEqual(result.constraints['status'].value, 'active')

    def test_parse_rel_operator_multiple_fields(self):
        result = self.parser.parse({
            '$rel': {
                'status': {'$eq': 'active'},
                'type': {'$eq': 'premium'}
            }
        })
        self.assertIsInstance(result, RelOperator)
        self.assertEqual(len(result.constraints), 2)
        self.assertEqual(result.constraints['status'].value, 'active')
        self.assertEqual(result.constraints['type'].value, 'premium')

    def test_parse_rel_operator_nested(self):
        """$rel can contain nested $rel."""
        result = self.parser.parse({
            '$rel': {
                'department': {
                    '$rel': {'name': {'$eq': 'IT'}}
                }
            }
        })
        self.assertIsInstance(result, RelOperator)
        self.assertIsInstance(result.constraints['department'], RelOperator)
        self.assertEqual(result.constraints['department'].constraints['name'].value, 'IT')

    def test_parse_rel_operator_with_implicit_eq(self):
        """$rel with scalar value uses implicit $eq."""
        result = self.parser.parse({'$rel': {'id': 42}})
        self.assertIsInstance(result, RelOperator)
        self.assertIsInstance(result.constraints['id'], EqOperator)
        self.assertEqual(result.constraints['id'].value, 42)


class TestQueryParserComposite(unittest.TestCase):
    """Tests for QueryParser.parse() with CompositeQuery."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_composite_query(self):
        result = self.parser.parse({
            'tenant_id': {'$eq': 15},
            'local_id': {'$eq': 27}
        })
        self.assertIsInstance(result, CompositeQuery)
        self.assertEqual(len(result.fields), 2)
        self.assertEqual(result.fields['tenant_id'].value, 15)
        self.assertEqual(result.fields['local_id'].value, 27)

    def test_parse_composite_query_with_implicit_eq(self):
        """Composite fields with scalar values use implicit $eq."""
        result = self.parser.parse({
            'tenant_id': 15,
            'local_id': 27
        })
        self.assertIsInstance(result, CompositeQuery)
        self.assertEqual(result.fields['tenant_id'].value, 15)
        self.assertEqual(result.fields['local_id'].value, 27)

    def test_parse_composite_query_nested(self):
        """CompositeQuery can contain nested composites."""
        result = self.parser.parse({
            'address': {
                'city': {'$eq': 'Moscow'},
                'country': {'$eq': 'Russia'}
            }
        })
        self.assertIsInstance(result, CompositeQuery)
        self.assertIsInstance(result.fields['address'], CompositeQuery)
        self.assertEqual(result.fields['address'].fields['city'].value, 'Moscow')


class TestQueryParserErrors(unittest.TestCase):
    """Tests for QueryParser.parse() error cases."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_empty_dict_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.parser.parse({})
        self.assertIn("Empty query", str(cm.exception))

    def test_parse_mixed_operators_and_fields_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.parser.parse({'$eq': 5, 'field': 10})
        self.assertIn("Cannot mix operators and fields", str(cm.exception))

    def test_parse_unknown_operator_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.parser.parse({'$unknown': 5})
        self.assertIn("Unknown operator", str(cm.exception))

    def test_parse_multiple_operators_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.parser.parse({'$eq': 5, '$rel': {}})
        self.assertIn("Only one operator per level", str(cm.exception))

    def test_parse_rel_with_non_dict_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.parser.parse({'$rel': 'invalid'})
        self.assertIn("$rel value must be dict", str(cm.exception))


class TestEqOperatorEquality(unittest.TestCase):
    """Tests for EqOperator equality and hashing."""

    def test_eq_operators_equal(self):
        eq1 = EqOperator(5)
        eq2 = EqOperator(5)
        self.assertEqual(eq1, eq2)

    def test_eq_operators_not_equal(self):
        eq1 = EqOperator(5)
        eq2 = EqOperator(10)
        self.assertNotEqual(eq1, eq2)

    def test_eq_operators_hashable(self):
        eq1 = EqOperator(5)
        eq2 = EqOperator(5)
        self.assertEqual(hash(eq1), hash(eq2))

    def test_eq_operators_in_set(self):
        eq1 = EqOperator(5)
        eq2 = EqOperator(5)
        s = {eq1}
        self.assertIn(eq2, s)


class TestRelOperatorEquality(unittest.TestCase):
    """Tests for RelOperator equality and hashing."""

    def test_rel_operators_equal(self):
        rel1 = RelOperator({'status': EqOperator('active')})
        rel2 = RelOperator({'status': EqOperator('active')})
        self.assertEqual(rel1, rel2)

    def test_rel_operators_not_equal(self):
        rel1 = RelOperator({'status': EqOperator('active')})
        rel2 = RelOperator({'status': EqOperator('inactive')})
        self.assertNotEqual(rel1, rel2)

    def test_rel_operators_hashable(self):
        rel1 = RelOperator({'status': EqOperator('active')})
        rel2 = RelOperator({'status': EqOperator('active')})
        self.assertEqual(hash(rel1), hash(rel2))


class TestCompositeQueryEquality(unittest.TestCase):
    """Tests for CompositeQuery equality and hashing."""

    def test_composite_queries_equal(self):
        cq1 = CompositeQuery({'a': EqOperator(1), 'b': EqOperator(2)})
        cq2 = CompositeQuery({'a': EqOperator(1), 'b': EqOperator(2)})
        self.assertEqual(cq1, cq2)

    def test_composite_queries_not_equal(self):
        cq1 = CompositeQuery({'a': EqOperator(1)})
        cq2 = CompositeQuery({'a': EqOperator(2)})
        self.assertNotEqual(cq1, cq2)

    def test_composite_queries_hashable(self):
        cq1 = CompositeQuery({'a': EqOperator(1), 'b': EqOperator(2)})
        cq2 = CompositeQuery({'a': EqOperator(1), 'b': EqOperator(2)})
        self.assertEqual(hash(cq1), hash(cq2))


if __name__ == '__main__':
    unittest.main()
