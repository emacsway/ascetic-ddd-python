"""Tests for query visitors."""
import unittest

from ascetic_ddd.faker.domain.query.operators import (
    EqOperator, ComparisonOperator, InOperator, IsNullOperator, AndOperator,
    OrOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.domain.query.visitors import (
    QueryToDictVisitor,
    QueryToPlainValueVisitor,
    query_to_dict,
    query_to_plain_value,
)


class TestQueryToDictVisitor(unittest.TestCase):
    """Tests for QueryToDictVisitor."""

    def test_visit_eq(self):
        visitor = QueryToDictVisitor()
        result = visitor.visit(EqOperator(5))
        self.assertEqual(result, {'$eq': 5})

    def test_visit_eq_none(self):
        visitor = QueryToDictVisitor()
        result = visitor.visit(EqOperator(None))
        self.assertEqual(result, {'$eq': None})

    def test_visit_eq_dict(self):
        """EqOperator with dict value."""
        visitor = QueryToDictVisitor()
        result = visitor.visit(EqOperator({'a': 1, 'b': 2}))
        self.assertEqual(result, {'$eq': {'a': 1, 'b': 2}})

    def test_visit_rel(self):
        visitor = QueryToDictVisitor()
        query = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        result = visitor.visit(query)
        self.assertEqual(result, {'$rel': {'status': {'$eq': 'active'}}})

    def test_visit_rel_multiple_fields(self):
        visitor = QueryToDictVisitor()
        query = RelOperator(CompositeQuery({
            'status': EqOperator('active'),
            'type': EqOperator('premium')
        }))
        result = visitor.visit(query)
        self.assertEqual(result, {
            '$rel': {
                'status': {'$eq': 'active'},
                'type': {'$eq': 'premium'}
            }
        })

    def test_visit_rel_nested(self):
        visitor = QueryToDictVisitor()
        query = RelOperator(CompositeQuery({
            'department': RelOperator(CompositeQuery({'name': EqOperator('IT')}))
        }))
        result = visitor.visit(query)
        self.assertEqual(result, {
            '$rel': {
                'department': {'$rel': {'name': {'$eq': 'IT'}}}
            }
        })

    def test_visit_composite(self):
        visitor = QueryToDictVisitor()
        query = CompositeQuery({'a': EqOperator(1), 'b': EqOperator(2)})
        result = visitor.visit(query)
        self.assertEqual(result, {'a': {'$eq': 1}, 'b': {'$eq': 2}})

    def test_visit_composite_nested(self):
        visitor = QueryToDictVisitor()
        query = CompositeQuery({
            'address': CompositeQuery({
                'city': EqOperator('Moscow'),
                'country': EqOperator('Russia')
            })
        })
        result = visitor.visit(query)
        self.assertEqual(result, {
            'address': {
                'city': {'$eq': 'Moscow'},
                'country': {'$eq': 'Russia'}
            }
        })


class TestQueryToDictVisitorComparison(unittest.TestCase):
    """Tests for QueryToDictVisitor with ComparisonOperator."""

    def test_visit_gt(self):
        visitor = QueryToDictVisitor()
        result = visitor.visit(ComparisonOperator('$gt', 10))
        self.assertEqual(result, {'$gt': 10})

    def test_visit_gte(self):
        visitor = QueryToDictVisitor()
        result = visitor.visit(ComparisonOperator('$gte', 0))
        self.assertEqual(result, {'$gte': 0})

    def test_visit_lt(self):
        visitor = QueryToDictVisitor()
        result = visitor.visit(ComparisonOperator('$lt', 100))
        self.assertEqual(result, {'$lt': 100})

    def test_visit_lte(self):
        visitor = QueryToDictVisitor()
        result = visitor.visit(ComparisonOperator('$lte', 99))
        self.assertEqual(result, {'$lte': 99})

    def test_visit_comparison_in_composite(self):
        visitor = QueryToDictVisitor()
        query = CompositeQuery({
            'age': ComparisonOperator('$gt', 18),
            'status': EqOperator('active'),
        })
        result = visitor.visit(query)
        self.assertEqual(result, {
            'age': {'$gt': 18},
            'status': {'$eq': 'active'},
        })


class TestQueryToDictVisitorOr(unittest.TestCase):
    """Tests for QueryToDictVisitor with OrOperator."""

    def test_visit_or_with_eq(self):
        visitor = QueryToDictVisitor()
        query = OrOperator((EqOperator('a'), EqOperator('b')))
        result = visitor.visit(query)
        self.assertEqual(result, {'$or': [{'$eq': 'a'}, {'$eq': 'b'}]})

    def test_visit_or_with_composite(self):
        visitor = QueryToDictVisitor()
        query = OrOperator((
            CompositeQuery({'x': EqOperator(1)}),
            CompositeQuery({'y': EqOperator(2)}),
        ))
        result = visitor.visit(query)
        self.assertEqual(result, {
            '$or': [
                {'x': {'$eq': 1}},
                {'y': {'$eq': 2}},
            ]
        })

    def test_visit_or_with_comparison(self):
        visitor = QueryToDictVisitor()
        query = OrOperator((
            ComparisonOperator('$lt', 18),
            ComparisonOperator('$gt', 65),
        ))
        result = visitor.visit(query)
        self.assertEqual(result, {
            '$or': [{'$lt': 18}, {'$gt': 65}]
        })

    def test_visit_or_three_operands(self):
        visitor = QueryToDictVisitor()
        query = OrOperator((EqOperator(1), EqOperator(2), EqOperator(3)))
        result = visitor.visit(query)
        self.assertEqual(result, {'$or': [{'$eq': 1}, {'$eq': 2}, {'$eq': 3}]})

    def test_visit_or_in_composite(self):
        visitor = QueryToDictVisitor()
        query = CompositeQuery({
            'status': OrOperator((EqOperator('active'), EqOperator('pending'))),
        })
        result = visitor.visit(query)
        self.assertEqual(result, {
            'status': {'$or': [{'$eq': 'active'}, {'$eq': 'pending'}]}
        })


class TestQueryToDictVisitorIn(unittest.TestCase):
    """Tests for QueryToDictVisitor with InOperator."""

    def test_visit_in(self):
        visitor = QueryToDictVisitor()
        result = visitor.visit(InOperator(('active', 'pending')))
        self.assertEqual(result, {'$in': ['active', 'pending']})

    def test_visit_in_single(self):
        visitor = QueryToDictVisitor()
        result = visitor.visit(InOperator((42,)))
        self.assertEqual(result, {'$in': [42]})

    def test_visit_in_composite(self):
        visitor = QueryToDictVisitor()
        query = CompositeQuery({'status': InOperator(('active', 'pending'))})
        result = visitor.visit(query)
        self.assertEqual(result, {'status': {'$in': ['active', 'pending']}})


class TestQueryToDictVisitorIsNull(unittest.TestCase):
    """Tests for QueryToDictVisitor with IsNullOperator."""

    def test_visit_is_null_true(self):
        visitor = QueryToDictVisitor()
        result = visitor.visit(IsNullOperator(True))
        self.assertEqual(result, {'$is_null': True})

    def test_visit_is_null_false(self):
        visitor = QueryToDictVisitor()
        result = visitor.visit(IsNullOperator(False))
        self.assertEqual(result, {'$is_null': False})

    def test_visit_is_null_in_composite(self):
        visitor = QueryToDictVisitor()
        query = CompositeQuery({'name': IsNullOperator(True)})
        result = visitor.visit(query)
        self.assertEqual(result, {'name': {'$is_null': True}})


class TestQueryToDictVisitorAnd(unittest.TestCase):
    """Tests for QueryToDictVisitor with AndOperator."""

    def test_visit_and_range(self):
        visitor = QueryToDictVisitor()
        query = AndOperator((
            ComparisonOperator('$gt', 5),
            ComparisonOperator('$lt', 10),
        ))
        result = visitor.visit(query)
        self.assertEqual(result, {'$gt': 5, '$lt': 10})

    def test_visit_and_in_composite(self):
        visitor = QueryToDictVisitor()
        query = CompositeQuery({
            'age': AndOperator((
                ComparisonOperator('$gt', 5),
                ComparisonOperator('$lt', 10),
            ))
        })
        result = visitor.visit(query)
        self.assertEqual(result, {'age': {'$gt': 5, '$lt': 10}})

    def test_visit_and_three_operands(self):
        visitor = QueryToDictVisitor()
        query = AndOperator((
            ComparisonOperator('$gt', 0),
            ComparisonOperator('$lt', 100),
            ComparisonOperator('$ne', 50),
        ))
        result = visitor.visit(query)
        self.assertEqual(result, {'$gt': 0, '$lt': 100, '$ne': 50})


class TestQueryToPlainValueVisitor(unittest.TestCase):
    """Tests for QueryToPlainValueVisitor."""

    def test_visit_eq(self):
        visitor = QueryToPlainValueVisitor()
        result = visitor.visit(EqOperator(5))
        self.assertEqual(result, 5)

    def test_visit_eq_none(self):
        visitor = QueryToPlainValueVisitor()
        result = visitor.visit(EqOperator(None))
        self.assertIsNone(result)

    def test_visit_eq_dict(self):
        """EqOperator with dict value returns the dict as-is."""
        visitor = QueryToPlainValueVisitor()
        result = visitor.visit(EqOperator({'a': 1, 'b': 2}))
        self.assertEqual(result, {'a': 1, 'b': 2})

    def test_visit_rel(self):
        visitor = QueryToPlainValueVisitor()
        query = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        result = visitor.visit(query)
        self.assertEqual(result, {'status': 'active'})

    def test_visit_rel_multiple_fields(self):
        visitor = QueryToPlainValueVisitor()
        query = RelOperator(CompositeQuery({
            'status': EqOperator('active'),
            'type': EqOperator('premium')
        }))
        result = visitor.visit(query)
        self.assertEqual(result, {'status': 'active', 'type': 'premium'})

    def test_visit_rel_nested(self):
        visitor = QueryToPlainValueVisitor()
        query = RelOperator(CompositeQuery({
            'department': RelOperator(CompositeQuery({'name': EqOperator('IT')}))
        }))
        result = visitor.visit(query)
        self.assertEqual(result, {'department': {'name': 'IT'}})

    def test_visit_composite(self):
        visitor = QueryToPlainValueVisitor()
        query = CompositeQuery({'a': EqOperator(1), 'b': EqOperator(2)})
        result = visitor.visit(query)
        self.assertEqual(result, {'a': 1, 'b': 2})

    def test_visit_composite_nested(self):
        visitor = QueryToPlainValueVisitor()
        query = CompositeQuery({
            'address': CompositeQuery({
                'city': EqOperator('Moscow'),
                'country': EqOperator('Russia')
            })
        })
        result = visitor.visit(query)
        self.assertEqual(result, {'address': {'city': 'Moscow', 'country': 'Russia'}})


class TestQueryToPlainValueVisitorComparison(unittest.TestCase):
    """Tests for QueryToPlainValueVisitor with ComparisonOperator."""

    def test_visit_gt(self):
        visitor = QueryToPlainValueVisitor()
        result = visitor.visit(ComparisonOperator('$gt', 10))
        self.assertEqual(result, {'$gt': 10})

    def test_visit_gte(self):
        visitor = QueryToPlainValueVisitor()
        result = visitor.visit(ComparisonOperator('$gte', 0))
        self.assertEqual(result, {'$gte': 0})

    def test_visit_lt(self):
        visitor = QueryToPlainValueVisitor()
        result = visitor.visit(ComparisonOperator('$lt', 100))
        self.assertEqual(result, {'$lt': 100})

    def test_visit_lte(self):
        visitor = QueryToPlainValueVisitor()
        result = visitor.visit(ComparisonOperator('$lte', 99))
        self.assertEqual(result, {'$lte': 99})

    def test_visit_comparison_in_composite(self):
        visitor = QueryToPlainValueVisitor()
        query = CompositeQuery({
            'age': ComparisonOperator('$gt', 18),
            'status': EqOperator('active'),
        })
        result = visitor.visit(query)
        self.assertEqual(result, {
            'age': {'$gt': 18},
            'status': 'active',
        })


class TestQueryToPlainValueVisitorIn(unittest.TestCase):
    """Tests for QueryToPlainValueVisitor with InOperator."""

    def test_visit_in(self):
        visitor = QueryToPlainValueVisitor()
        result = visitor.visit(InOperator(('active', 'pending')))
        self.assertEqual(result, {'$in': ['active', 'pending']})

    def test_visit_in_composite(self):
        visitor = QueryToPlainValueVisitor()
        query = CompositeQuery({'status': InOperator(('active', 'pending'))})
        result = visitor.visit(query)
        self.assertEqual(result, {'status': {'$in': ['active', 'pending']}})


class TestQueryToPlainValueVisitorIsNull(unittest.TestCase):
    """Tests for QueryToPlainValueVisitor with IsNullOperator."""

    def test_visit_is_null_true(self):
        visitor = QueryToPlainValueVisitor()
        result = visitor.visit(IsNullOperator(True))
        self.assertEqual(result, {'$is_null': True})

    def test_visit_is_null_false(self):
        visitor = QueryToPlainValueVisitor()
        result = visitor.visit(IsNullOperator(False))
        self.assertEqual(result, {'$is_null': False})

    def test_visit_is_null_in_composite(self):
        visitor = QueryToPlainValueVisitor()
        query = CompositeQuery({'name': IsNullOperator(True)})
        result = visitor.visit(query)
        self.assertEqual(result, {'name': {'$is_null': True}})


class TestQueryToPlainValueVisitorAnd(unittest.TestCase):
    """Tests for QueryToPlainValueVisitor with AndOperator."""

    def test_visit_and_range(self):
        visitor = QueryToPlainValueVisitor()
        query = AndOperator((
            ComparisonOperator('$gt', 5),
            ComparisonOperator('$lt', 10),
        ))
        result = visitor.visit(query)
        self.assertEqual(result, {'$gt': 5, '$lt': 10})

    def test_visit_and_in_composite(self):
        visitor = QueryToPlainValueVisitor()
        query = CompositeQuery({
            'age': AndOperator((
                ComparisonOperator('$gt', 5),
                ComparisonOperator('$lt', 10),
            ))
        })
        result = visitor.visit(query)
        self.assertEqual(result, {'age': {'$gt': 5, '$lt': 10}})


class TestQueryToPlainValueVisitorOr(unittest.TestCase):
    """Tests for QueryToPlainValueVisitor with OrOperator."""

    def test_visit_or_with_eq(self):
        visitor = QueryToPlainValueVisitor()
        query = OrOperator((EqOperator('a'), EqOperator('b')))
        result = visitor.visit(query)
        self.assertEqual(result, {'$or': ['a', 'b']})

    def test_visit_or_with_composite(self):
        visitor = QueryToPlainValueVisitor()
        query = OrOperator((
            CompositeQuery({'x': EqOperator(1)}),
            CompositeQuery({'y': EqOperator(2)}),
        ))
        result = visitor.visit(query)
        self.assertEqual(result, {
            '$or': [{'x': 1}, {'y': 2}]
        })

    def test_visit_or_with_comparison(self):
        visitor = QueryToPlainValueVisitor()
        query = OrOperator((
            ComparisonOperator('$lt', 18),
            ComparisonOperator('$gt', 65),
        ))
        result = visitor.visit(query)
        self.assertEqual(result, {
            '$or': [{'$lt': 18}, {'$gt': 65}]
        })

    def test_visit_or_three_operands(self):
        visitor = QueryToPlainValueVisitor()
        query = OrOperator((EqOperator(1), EqOperator(2), EqOperator(3)))
        result = visitor.visit(query)
        self.assertEqual(result, {'$or': [1, 2, 3]})

    def test_visit_or_in_composite(self):
        visitor = QueryToPlainValueVisitor()
        query = CompositeQuery({
            'status': OrOperator((EqOperator('active'), EqOperator('pending'))),
        })
        result = visitor.visit(query)
        self.assertEqual(result, {
            'status': {'$or': ['active', 'pending']}
        })


class TestConvenienceFunctions(unittest.TestCase):
    """Tests for convenience functions query_to_dict and query_to_plain_value."""

    def test_query_to_dict_eq(self):
        result = query_to_dict(EqOperator(5))
        self.assertEqual(result, {'$eq': 5})

    def test_query_to_dict_rel(self):
        query = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        result = query_to_dict(query)
        self.assertEqual(result, {'$rel': {'status': {'$eq': 'active'}}})

    def test_query_to_dict_composite(self):
        query = CompositeQuery({'a': EqOperator(1)})
        result = query_to_dict(query)
        self.assertEqual(result, {'a': {'$eq': 1}})

    def test_query_to_plain_value_eq(self):
        result = query_to_plain_value(EqOperator(5))
        self.assertEqual(result, 5)

    def test_query_to_plain_value_rel(self):
        query = RelOperator(CompositeQuery({'status': EqOperator('active')}))
        result = query_to_plain_value(query)
        self.assertEqual(result, {'status': 'active'})

    def test_query_to_plain_value_composite(self):
        query = CompositeQuery({'a': EqOperator(1)})
        result = query_to_plain_value(query)
        self.assertEqual(result, {'a': 1})


if __name__ == '__main__':
    unittest.main()
