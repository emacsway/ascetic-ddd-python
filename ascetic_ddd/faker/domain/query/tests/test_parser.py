"""Tests for QueryParser."""
import unittest

from ascetic_ddd.faker.domain.query.parser import QueryParser
from ascetic_ddd.faker.domain.query.operators import (
    EqOperator, ComparisonOperator, InOperator, AndOperator, OrOperator,
    RelOperator, CompositeQuery
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
        """$eq with dict is fully parsed into EqOperator(CompositeQuery(...))."""
        result = self.parser.parse({'$eq': {'tenant_id': 1, 'local_id': 2}})
        self.assertIsInstance(result, EqOperator)
        self.assertIsInstance(result.value, CompositeQuery)
        self.assertEqual(result.value.fields['tenant_id'].value, 1)
        self.assertEqual(result.value.fields['local_id'].value, 2)


class TestQueryParserRel(unittest.TestCase):
    """Tests for QueryParser.parse() with $rel operator."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_rel_operator_simple(self):
        result = self.parser.parse({'$rel': {'status': {'$eq': 'active'}}})
        self.assertIsInstance(result, RelOperator)
        self.assertIn('status', result.query.fields)
        self.assertIsInstance(result.query.fields['status'], EqOperator)
        self.assertEqual(result.query.fields['status'].value, 'active')

    def test_parse_rel_operator_multiple_fields(self):
        result = self.parser.parse({
            '$rel': {
                'status': {'$eq': 'active'},
                'type': {'$eq': 'premium'}
            }
        })
        self.assertIsInstance(result, RelOperator)
        self.assertEqual(len(result.query.fields), 2)
        self.assertEqual(result.query.fields['status'].value, 'active')
        self.assertEqual(result.query.fields['type'].value, 'premium')

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
        self.assertIsInstance(result.query.fields['department'], RelOperator)
        self.assertEqual(result.query.fields['department'].query.fields['name'].value, 'IT')

    def test_parse_rel_operator_with_implicit_eq(self):
        """$rel with scalar value uses implicit $eq."""
        result = self.parser.parse({'$rel': {'id': 42}})
        self.assertIsInstance(result, RelOperator)
        self.assertIsInstance(result.query.fields['id'], EqOperator)
        self.assertEqual(result.query.fields['id'].value, 42)


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


class TestQueryParserComparison(unittest.TestCase):
    """Tests for QueryParser.parse() with comparison operators."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_gt(self):
        result = self.parser.parse({'$gt': 10})
        self.assertIsInstance(result, ComparisonOperator)
        self.assertEqual(result.op, '$gt')
        self.assertEqual(result.value, 10)

    def test_parse_gte(self):
        result = self.parser.parse({'$gte': 0})
        self.assertIsInstance(result, ComparisonOperator)
        self.assertEqual(result.op, '$gte')
        self.assertEqual(result.value, 0)

    def test_parse_lt(self):
        result = self.parser.parse({'$lt': 100})
        self.assertIsInstance(result, ComparisonOperator)
        self.assertEqual(result.op, '$lt')
        self.assertEqual(result.value, 100)

    def test_parse_lte(self):
        result = self.parser.parse({'$lte': 99})
        self.assertIsInstance(result, ComparisonOperator)
        self.assertEqual(result.op, '$lte')
        self.assertEqual(result.value, 99)

    def test_parse_comparison_in_composite(self):
        result = self.parser.parse({
            'age': {'$gt': 18},
            'status': {'$eq': 'active'}
        })
        self.assertIsInstance(result, CompositeQuery)
        self.assertIsInstance(result.fields['age'], ComparisonOperator)
        self.assertEqual(result.fields['age'].op, '$gt')
        self.assertEqual(result.fields['age'].value, 18)
        self.assertIsInstance(result.fields['status'], EqOperator)


class TestQueryParserOr(unittest.TestCase):
    """Tests for QueryParser.parse() with $or operator."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_or_simple(self):
        result = self.parser.parse({
            '$or': [
                {'status': {'$eq': 'active'}},
                {'status': {'$eq': 'pending'}}
            ]
        })
        self.assertIsInstance(result, OrOperator)
        self.assertEqual(len(result.operands), 2)
        self.assertIsInstance(result.operands[0], CompositeQuery)
        self.assertIsInstance(result.operands[1], CompositeQuery)

    def test_parse_or_with_scalars(self):
        result = self.parser.parse({
            '$or': [{'$eq': 1}, {'$eq': 2}]
        })
        self.assertIsInstance(result, OrOperator)
        self.assertEqual(result.operands[0].value, 1)
        self.assertEqual(result.operands[1].value, 2)

    def test_parse_or_three_operands(self):
        result = self.parser.parse({
            '$or': [{'$eq': 'a'}, {'$eq': 'b'}, {'$eq': 'c'}]
        })
        self.assertIsInstance(result, OrOperator)
        self.assertEqual(len(result.operands), 3)

    def test_parse_or_in_composite(self):
        result = self.parser.parse({
            'priority': {'$or': [{'$eq': 'high'}, {'$eq': 'critical'}]}
        })
        self.assertIsInstance(result, CompositeQuery)
        self.assertIsInstance(result.fields['priority'], OrOperator)

    def test_parse_or_with_comparison(self):
        result = self.parser.parse({
            '$or': [
                {'age': {'$gt': 18}},
                {'vip': {'$eq': True}}
            ]
        })
        self.assertIsInstance(result, OrOperator)
        age_op = result.operands[0].fields['age']
        self.assertIsInstance(age_op, ComparisonOperator)
        self.assertEqual(age_op.op, '$gt')

    def test_parse_or_non_list_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.parser.parse({'$or': 'invalid'})
        self.assertIn("$or value must be list", str(cm.exception))

    def test_parse_or_one_operand_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.parser.parse({'$or': [{'$eq': 1}]})
        self.assertIn("at least 2 operands", str(cm.exception))

    def test_parse_or_empty_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.parser.parse({'$or': []})
        self.assertIn("at least 2 operands", str(cm.exception))


class TestQueryParserNe(unittest.TestCase):
    """Tests for QueryParser.parse() with $ne operator."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_ne(self):
        result = self.parser.parse({'$ne': 'deleted'})
        self.assertIsInstance(result, ComparisonOperator)
        self.assertEqual(result.op, '$ne')
        self.assertEqual(result.value, 'deleted')

    def test_parse_ne_in_composite(self):
        result = self.parser.parse({'status': {'$ne': 'deleted'}})
        self.assertIsInstance(result, CompositeQuery)
        self.assertIsInstance(result.fields['status'], ComparisonOperator)
        self.assertEqual(result.fields['status'].op, '$ne')
        self.assertEqual(result.fields['status'].value, 'deleted')


class TestQueryParserIn(unittest.TestCase):
    """Tests for QueryParser.parse() with $in operator."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_in_simple(self):
        result = self.parser.parse({'$in': ['active', 'pending']})
        self.assertIsInstance(result, InOperator)
        self.assertEqual(result.values, ('active', 'pending'))

    def test_parse_in_single(self):
        result = self.parser.parse({'$in': [42]})
        self.assertIsInstance(result, InOperator)
        self.assertEqual(result.values, (42,))

    def test_parse_in_composite(self):
        result = self.parser.parse({'status': {'$in': ['active', 'pending']}})
        self.assertIsInstance(result, CompositeQuery)
        self.assertIsInstance(result.fields['status'], InOperator)
        self.assertEqual(result.fields['status'].values, ('active', 'pending'))

    def test_parse_in_non_list_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.parser.parse({'$in': 'invalid'})
        self.assertIn("$in value must be list", str(cm.exception))

    def test_parse_in_empty_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.parser.parse({'$in': []})
        self.assertIn("at least 1 value", str(cm.exception))


class TestQueryParserAnd(unittest.TestCase):
    """Tests for QueryParser.parse() with implicit AND (multiple operators)."""

    def setUp(self):
        self.parser = QueryParser()

    def test_parse_range(self):
        """{'$gt': 5, '$lt': 10} -> AndOperator."""
        result = self.parser.parse({'$gt': 5, '$lt': 10})
        self.assertIsInstance(result, AndOperator)
        self.assertEqual(len(result.operands), 2)
        ops = {op.op: op.value for op in result.operands}
        self.assertEqual(ops, {'$gt': 5, '$lt': 10})

    def test_parse_range_in_composite(self):
        """{'age': {'$gt': 5, '$lt': 10}} -> CompositeQuery with AndOperator."""
        result = self.parser.parse({'age': {'$gt': 5, '$lt': 10}})
        self.assertIsInstance(result, CompositeQuery)
        self.assertIsInstance(result.fields['age'], AndOperator)
        self.assertEqual(len(result.fields['age'].operands), 2)

    def test_parse_three_operators(self):
        result = self.parser.parse({'$gt': 0, '$lt': 100, '$ne': 50})
        self.assertIsInstance(result, AndOperator)
        self.assertEqual(len(result.operands), 3)

    def test_parse_ne_with_comparison(self):
        result = self.parser.parse({'$ne': 'deleted', '$gt': 0})
        self.assertIsInstance(result, AndOperator)
        self.assertEqual(len(result.operands), 2)


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

    def test_parse_multiple_operators_creates_and(self):
        """Multiple operators at same level create AndOperator."""
        result = self.parser.parse({'$gt': 5, '$lt': 10})
        self.assertIsInstance(result, AndOperator)
        self.assertEqual(len(result.operands), 2)

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
        rel1 = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        rel2 = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        self.assertEqual(rel1, rel2)

    def test_rel_operators_not_equal(self):
        rel1 = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        rel2 = RelOperator(CompositeQuery({'status': EqOperator('inactive')}))
        self.assertNotEqual(rel1, rel2)

    def test_rel_operators_hashable(self):
        rel1 = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        rel2 = RelOperator(CompositeQuery({'status': EqOperator('active')}))
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
