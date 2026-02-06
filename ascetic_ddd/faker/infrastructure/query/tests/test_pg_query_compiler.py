"""Tests for PgQueryCompiler."""
import unittest

from ascetic_ddd.faker.domain.query.operators import (
    EqOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.infrastructure.query.pg_query_compiler import PgQueryCompiler


class TestPgQueryCompilerEq(unittest.TestCase):
    """Tests for compiling EqOperator."""

    def test_compile_eq_scalar(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(EqOperator(42))

        self.assertEqual(sql, "value @> %s")
        self.assertEqual(len(params), 1)
        # params[0] is Jsonb wrapper

    def test_compile_eq_string(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(EqOperator("active"))

        self.assertEqual(sql, "value @> %s")
        self.assertEqual(len(params), 1)

    def test_compile_eq_dict(self):
        """EqOperator with composite value."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(EqOperator({'tenant': 1, 'local': 2}))

        self.assertEqual(sql, "value @> %s")
        self.assertEqual(len(params), 1)

    def test_compile_eq_custom_target(self):
        compiler = PgQueryCompiler(target_value_expr="rt.value")
        sql, params = compiler.compile(EqOperator(42))

        self.assertEqual(sql, "rt.value @> %s")


class TestPgQueryCompilerComposite(unittest.TestCase):
    """Tests for compiling CompositeQuery."""

    def test_compile_composite_single_field(self):
        compiler = PgQueryCompiler()
        query = CompositeQuery({'status': EqOperator('active')})
        sql, params = compiler.compile(query)

        self.assertEqual(sql, "value @> %s")
        self.assertEqual(len(params), 1)

    def test_compile_composite_multiple_fields_collapsed(self):
        """All $eq fields should collapse into single @>."""
        compiler = PgQueryCompiler()
        query = CompositeQuery({
            'status': EqOperator('active'),
            'type': EqOperator('premium'),
            'count': EqOperator(10)
        })
        sql, params = compiler.compile(query)

        # All fields collapsed into one @>
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(len(params), 1)

    def test_compile_composite_nested(self):
        """Nested CompositeQueries."""
        compiler = PgQueryCompiler()
        query = CompositeQuery({
            'address': CompositeQuery({
                'city': EqOperator('Moscow'),
                'country': EqOperator('Russia')
            })
        })
        sql, params = compiler.compile(query)

        # Outer composite generates @>, nested composite is visited separately
        self.assertIn("@>", sql)


class TestPgQueryCompilerRel(unittest.TestCase):
    """Tests for compiling RelOperator without provider."""

    def test_compile_rel_without_provider_collapses(self):
        """Without provider, $rel collapses to @>."""
        compiler = PgQueryCompiler()
        query = RelOperator({
            'status': EqOperator('active'),
            'type': EqOperator('premium')
        })
        sql, params = compiler.compile(query)

        self.assertEqual(sql, "value @> %s")
        self.assertEqual(len(params), 1)

    def test_compile_rel_nested_without_provider(self):
        """Nested $rel without provider."""
        compiler = PgQueryCompiler()
        query = RelOperator({
            'department': RelOperator({
                'name': EqOperator('IT')
            })
        })
        sql, params = compiler.compile(query)

        self.assertEqual(sql, "value @> %s")
        self.assertEqual(len(params), 1)


class TestPgQueryCompilerCollectEqValues(unittest.TestCase):
    """Tests for _collect_eq_values helper."""

    def test_collect_from_eq(self):
        compiler = PgQueryCompiler()
        result = compiler._collect_eq_values(EqOperator(42))
        self.assertEqual(result, 42)

    def test_collect_from_rel(self):
        compiler = PgQueryCompiler()
        query = RelOperator({
            'status': EqOperator('active'),
            'count': EqOperator(10)
        })
        result = compiler._collect_eq_values(query)
        self.assertEqual(result, {'status': 'active', 'count': 10})

    def test_collect_from_composite(self):
        compiler = PgQueryCompiler()
        query = CompositeQuery({
            'a': EqOperator(1),
            'b': EqOperator(2)
        })
        result = compiler._collect_eq_values(query)
        self.assertEqual(result, {'a': 1, 'b': 2})

    def test_collect_nested(self):
        compiler = PgQueryCompiler()
        query = RelOperator({
            'department': RelOperator({
                'name': EqOperator('IT'),
                'code': EqOperator('IT001')
            }),
            'status': EqOperator('active')
        })
        result = compiler._collect_eq_values(query)
        self.assertEqual(result, {
            'department': {'name': 'IT', 'code': 'IT001'},
            'status': 'active'
        })


class TestPgQueryCompilerReuse(unittest.TestCase):
    """Tests for compiler reuse."""

    def test_compile_resets_state(self):
        """Each compile() call should reset internal state."""
        compiler = PgQueryCompiler()

        # First compilation
        sql1, params1 = compiler.compile(EqOperator(1))
        self.assertEqual(len(params1), 1)

        # Second compilation should not accumulate
        sql2, params2 = compiler.compile(EqOperator(2))
        self.assertEqual(len(params2), 1)

    def test_compile_different_queries(self):
        compiler = PgQueryCompiler()

        sql1, _ = compiler.compile(EqOperator(1))
        sql2, _ = compiler.compile(CompositeQuery({'a': EqOperator(1)}))

        self.assertEqual(sql1, "value @> %s")
        self.assertEqual(sql2, "value @> %s")


if __name__ == '__main__':
    unittest.main()
