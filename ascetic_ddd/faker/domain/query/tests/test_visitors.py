"""Tests for query visitors."""
import unittest

from ascetic_ddd.faker.domain.query.operators import (
    EqOperator, RelOperator, CompositeQuery
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
