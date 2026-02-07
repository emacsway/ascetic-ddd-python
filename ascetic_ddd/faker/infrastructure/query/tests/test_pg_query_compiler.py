"""Tests for PgQueryCompiler."""
import unittest

from ascetic_ddd.faker.domain.query.operators import (
    EqOperator, ComparisonOperator, InOperator, AndOperator, OrOperator,
    RelOperator, CompositeQuery
)
from ascetic_ddd.faker.infrastructure.query.pg_query_compiler import PgQueryCompiler
from ascetic_ddd.faker.infrastructure.query.relation_resolver import (
    IRelationResolver, RelationInfo
)


class StubRelationResolver(IRelationResolver):
    """Test stub: resolves field names to table/pk info via a dict."""

    def __init__(self, relations: dict[str, tuple[str, str, 'StubRelationResolver | None']]):
        # relations: {field: (table, pk_field, nested_resolver)}
        self._relations = relations

    def resolve(self, field: str) -> RelationInfo | None:
        info = self._relations.get(field)
        if info is None:
            return None
        return RelationInfo(table=info[0], pk_field=info[1], nested_resolver=info[2])


class TestVisitEq(unittest.TestCase):

    def test_scalar(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(EqOperator(42))
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(len(params), 1)

    def test_string(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(EqOperator("active"))
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(len(params), 1)

    def test_dict_value(self):
        """EqOperator can contain dict (composite PK)."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(EqOperator({'tenant': 1, 'local': 2}))
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(params[0].obj, {'tenant': 1, 'local': 2})

    def test_custom_target_expr(self):
        compiler = PgQueryCompiler(target_value_expr="rt.value")
        sql, params = compiler.compile(EqOperator(42))
        self.assertEqual(sql, "rt.value @> %s")


class TestVisitComposite(unittest.TestCase):

    def test_single_eq(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(
            CompositeQuery({'status': EqOperator('active')})
        )
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(params[0].obj, {'status': 'active'})

    def test_multiple_eq_collapsed(self):
        """All EqOperators collapse into single @>."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': EqOperator('active'),
            'type': EqOperator('premium'),
        }))
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0].obj, {'status': 'active', 'type': 'premium'})

    def test_nested_composite_preserves_field(self):
        """Nested CompositeQuery preserves parent field name."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'address': CompositeQuery({
                'city': EqOperator('Moscow'),
                'country': EqOperator('Russia'),
            })
        }))
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(params[0].obj, {'address': {'city': 'Moscow', 'country': 'Russia'}})

    def test_eq_with_dict_value_in_composite(self):
        """EqOperator with dict value inside CompositeQuery."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'pk': EqOperator({'tenant': 1, 'local': 2}),
        }))
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(params[0].obj, {'pk': {'tenant': 1, 'local': 2}})

    def test_mixed_eq_and_nested_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': EqOperator('active'),
            'address': CompositeQuery({
                'city': EqOperator('Moscow'),
            })
        }))
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(params[0].obj, {'status': 'active', 'address': {'city': 'Moscow'}})

    def test_deeply_nested_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'a': CompositeQuery({
                'b': CompositeQuery({
                    'c': EqOperator(42),
                })
            })
        }))
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(params[0].obj, {'a': {'b': {'c': 42}}})


class TestVisitRel(unittest.TestCase):

    def test_without_resolver_raises(self):
        compiler = PgQueryCompiler()
        with self.assertRaises(TypeError):
            compiler.compile(RelOperator(CompositeQuery({
                'status': EqOperator('active'),
            })))

    def test_rel_field_without_resolver_raises(self):
        compiler = PgQueryCompiler()
        with self.assertRaises(TypeError):
            compiler.compile(CompositeQuery({
                'fk_id': RelOperator(CompositeQuery({
                    'name': EqOperator('IT'),
                }))
            }))

    def test_rel_simple_exists(self):
        """$rel with resolver generates EXISTS subquery."""
        resolver = StubRelationResolver({
            'company_id': ('companies', 'value_id', None),
        })
        compiler = PgQueryCompiler(relation_resolver=resolver)
        sql, params = compiler.compile(CompositeQuery({
            'company_id': RelOperator(CompositeQuery({
                'name': EqOperator('Acme'),
            }))
        }))
        self.assertIn("EXISTS", sql)
        self.assertIn("companies", sql)
        self.assertIn("rt1", sql)
        self.assertEqual(params[0].obj, {'name': 'Acme'})

    def test_rel_non_reference_fallback(self):
        """$rel on non-reference field falls back to @> containment."""
        resolver = StubRelationResolver({})  # no relations
        compiler = PgQueryCompiler(relation_resolver=resolver)
        sql, params = compiler.compile(CompositeQuery({
            'address': RelOperator(CompositeQuery({
                'city': EqOperator('Moscow'),
            }))
        }))
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(params[0].obj, {'address': {'city': 'Moscow'}})

    def test_rel_with_eq_fields(self):
        """$rel combined with regular $eq fields."""
        resolver = StubRelationResolver({
            'dept_id': ('departments', 'value_id', None),
        })
        compiler = PgQueryCompiler(relation_resolver=resolver)
        sql, params = compiler.compile(CompositeQuery({
            'status': EqOperator('active'),
            'name': EqOperator('John'),
            'dept_id': RelOperator(CompositeQuery({
                'type': EqOperator('engineering'),
            }))
        }))
        self.assertIn("value @> %s", sql)
        self.assertIn("EXISTS", sql)
        self.assertIn("departments", sql)


class TestVisitComparison(unittest.TestCase):

    def test_gt_in_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'age': ComparisonOperator('$gt', 18),
        }))
        self.assertEqual(sql, "value->'age' > %s")
        self.assertEqual(params, (18,))

    def test_gte_in_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'score': ComparisonOperator('$gte', 100),
        }))
        self.assertEqual(sql, "value->'score' >= %s")
        self.assertEqual(params, (100,))

    def test_lt_in_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'price': ComparisonOperator('$lt', 50),
        }))
        self.assertEqual(sql, "value->'price' < %s")
        self.assertEqual(params, (50,))

    def test_lte_in_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'count': ComparisonOperator('$lte', 0),
        }))
        self.assertEqual(sql, "value->'count' <= %s")
        self.assertEqual(params, (0,))

    def test_mixed_eq_and_comparison(self):
        """Eq collapsed into @>, comparison is separate."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': EqOperator('active'),
            'age': ComparisonOperator('$gt', 18),
        }))
        self.assertEqual(sql, "value @> %s AND value->'age' > %s")
        self.assertEqual(params[0].obj, {'status': 'active'})
        self.assertEqual(params[1], 18)

    def test_nested_comparison(self):
        """Comparison inside nested CompositeQuery uses JSON path."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'stats': CompositeQuery({
                'views': ComparisonOperator('$gte', 1000),
            })
        }))
        self.assertEqual(sql, "value->'stats'->'views' >= %s")
        self.assertEqual(params, (1000,))


class TestVisitOr(unittest.TestCase):

    def test_or_with_eq(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': OrOperator((
                EqOperator('active'),
                EqOperator('pending'),
            )),
        }))
        self.assertEqual(
            sql,
            "(value @> %s OR value @> %s)"
        )
        self.assertEqual(params[0].obj, {'status': 'active'})
        self.assertEqual(params[1].obj, {'status': 'pending'})

    def test_or_with_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'x': OrOperator((
                CompositeQuery({'a': EqOperator(1)}),
                CompositeQuery({'b': EqOperator(2)}),
            )),
        }))
        self.assertEqual(
            sql,
            "(value @> %s OR value @> %s)"
        )
        self.assertEqual(params[0].obj, {'x': {'a': 1}})
        self.assertEqual(params[1].obj, {'x': {'b': 2}})

    def test_or_with_comparison(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'age': OrOperator((
                ComparisonOperator('$lt', 18),
                ComparisonOperator('$gt', 65),
            )),
        }))
        self.assertEqual(
            sql,
            "(value->'age' < %s OR value->'age' > %s)"
        )
        self.assertEqual(params, (18, 65))

    def test_or_mixed_with_eq_field(self):
        """Or alongside regular Eq field."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'type': EqOperator('user'),
            'status': OrOperator((
                EqOperator('active'),
                EqOperator('pending'),
            )),
        }))
        self.assertIn("value @> %s", sql)
        self.assertIn("OR", sql)

    def test_or_three_operands(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'priority': OrOperator((
                EqOperator('low'),
                EqOperator('medium'),
                EqOperator('high'),
            )),
        }))
        self.assertEqual(sql.count("OR"), 2)
        self.assertEqual(len(params), 3)


class TestVisitNe(unittest.TestCase):

    def test_ne_bare(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(ComparisonOperator('$ne', 'deleted'))
        self.assertEqual(sql, "NOT (value @> %s)")
        self.assertEqual(params[0].obj, 'deleted')

    def test_ne_in_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': ComparisonOperator('$ne', 'deleted'),
        }))
        self.assertEqual(sql, "NOT (value @> %s)")
        self.assertEqual(params[0].obj, {'status': 'deleted'})

    def test_ne_nested(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'profile': CompositeQuery({
                'role': ComparisonOperator('$ne', 'admin'),
            })
        }))
        self.assertEqual(sql, "NOT (value @> %s)")
        self.assertEqual(params[0].obj, {'profile': {'role': 'admin'}})

    def test_ne_mixed_with_eq(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': EqOperator('active'),
            'role': ComparisonOperator('$ne', 'admin'),
        }))
        self.assertEqual(sql, "value @> %s AND NOT (value @> %s)")
        self.assertEqual(params[0].obj, {'status': 'active'})
        self.assertEqual(params[1].obj, {'role': 'admin'})


class TestVisitIn(unittest.TestCase):

    def test_in_bare(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(InOperator(('active', 'pending')))
        self.assertEqual(sql, "(value @> %s OR value @> %s)")
        self.assertEqual(params[0].obj, 'active')
        self.assertEqual(params[1].obj, 'pending')

    def test_in_single_value(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(InOperator((42,)))
        self.assertEqual(sql, "value @> %s")
        self.assertEqual(params[0].obj, 42)

    def test_in_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': InOperator(('active', 'pending')),
        }))
        self.assertEqual(sql, "(value @> %s OR value @> %s)")
        self.assertEqual(params[0].obj, {'status': 'active'})
        self.assertEqual(params[1].obj, {'status': 'pending'})

    def test_in_nested(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'profile': CompositeQuery({
                'role': InOperator(('admin', 'moderator')),
            })
        }))
        self.assertEqual(sql, "(value @> %s OR value @> %s)")
        self.assertEqual(params[0].obj, {'profile': {'role': 'admin'}})
        self.assertEqual(params[1].obj, {'profile': {'role': 'moderator'}})

    def test_in_mixed_with_eq(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'type': EqOperator('user'),
            'status': InOperator(('active', 'pending')),
        }))
        self.assertEqual(sql, "value @> %s AND (value @> %s OR value @> %s)")
        self.assertEqual(params[0].obj, {'type': 'user'})
        self.assertEqual(params[1].obj, {'status': 'active'})
        self.assertEqual(params[2].obj, {'status': 'pending'})


class TestVisitAnd(unittest.TestCase):

    def test_and_range(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'age': AndOperator((
                ComparisonOperator('$gt', 5),
                ComparisonOperator('$lt', 10),
            ))
        }))
        self.assertEqual(sql, "value->'age' > %s AND value->'age' < %s")
        self.assertEqual(params, (5, 10))

    def test_and_ne_with_gt(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'age': AndOperator((
                ComparisonOperator('$ne', 0),
                ComparisonOperator('$gt', 18),
            ))
        }))
        self.assertEqual(sql, "NOT (value @> %s) AND value->'age' > %s")
        self.assertEqual(params[0].obj, {'age': 0})
        self.assertEqual(params[1], 18)

    def test_and_mixed_with_eq_field(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': EqOperator('active'),
            'age': AndOperator((
                ComparisonOperator('$gte', 18),
                ComparisonOperator('$lt', 65),
            ))
        }))
        self.assertEqual(sql, "value @> %s AND value->'age' >= %s AND value->'age' < %s")
        self.assertEqual(params[0].obj, {'status': 'active'})
        self.assertEqual(params[1], 18)
        self.assertEqual(params[2], 65)


class TestToDict(unittest.TestCase):

    def test_eq(self):
        self.assertEqual(PgQueryCompiler._to_dict(EqOperator(42)), 42)

    def test_composite(self):
        result = PgQueryCompiler._to_dict(CompositeQuery({
            'a': EqOperator(1),
            'b': EqOperator(2)
        }))
        self.assertEqual(result, {'a': 1, 'b': 2})

    def test_nested_composite(self):
        result = PgQueryCompiler._to_dict(CompositeQuery({
            'address': CompositeQuery({'city': EqOperator('Moscow')}),
            'status': EqOperator('active')
        }))
        self.assertEqual(result, {'address': {'city': 'Moscow'}, 'status': 'active'})

    def test_rel_returns_none(self):
        result = PgQueryCompiler._to_dict(RelOperator(CompositeQuery({
            'status': EqOperator('active'),
        })))
        self.assertIsNone(result)


class TestCompilerReuse(unittest.TestCase):

    def test_compile_resets_state(self):
        compiler = PgQueryCompiler()
        _, params1 = compiler.compile(EqOperator(1))
        self.assertEqual(len(params1), 1)
        _, params2 = compiler.compile(EqOperator(2))
        self.assertEqual(len(params2), 1)


class TestCascadingRelations(unittest.TestCase):
    """Three-table cascade: employees -> companies -> countries.

    Each level has 2 $eq + 1 other operator.
    Level 2 (companies) has $or where both branches reference level 3 (countries).
    """

    def _make_resolvers(self):
        country_resolver = StubRelationResolver({})
        company_resolver = StubRelationResolver({
            'country_id': ('countries', 'value_id', country_resolver),
        })
        employee_resolver = StubRelationResolver({
            'company_id': ('companies', 'value_id', company_resolver),
        })
        return employee_resolver

    def test_three_table_cascade(self):
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        # Level 1 (employees): 2 $eq + 1 $gt
        # Level 2 (companies): 2 $eq + $or with two $rel to countries
        # Level 3 (countries): $eq inside each $or branch
        query = CompositeQuery({
            'name': EqOperator('John'),
            'status': EqOperator('active'),
            'age': ComparisonOperator('$gt', 25),
            'company_id': RelOperator(CompositeQuery({
                'type': EqOperator('tech'),
                'size': EqOperator('large'),
                'revenue': ComparisonOperator('$gte', 1000000),
                'country_id': OrOperator((
                    RelOperator(CompositeQuery({
                        'code': EqOperator('US'),
                    })),
                    RelOperator(CompositeQuery({
                        'code': EqOperator('UK'),
                    })),
                )),
            })),
        })

        sql, params = compiler.compile(query)

        # Employees level: @> for collapsed eq + $gt + EXISTS for company
        self.assertIn("value @> %s", sql)
        self.assertIn("value->'age' > %s", sql)

        # Companies level: EXISTS with companies table
        self.assertIn("EXISTS (SELECT 1 FROM companies", sql)

        # Countries level: two nested EXISTS with countries table
        self.assertEqual(sql.count("EXISTS (SELECT 1 FROM countries"), 2)

        # All aliases must be unique (rt1, rt2, rt3)
        self.assertIn("rt1", sql)
        self.assertIn("rt2", sql)
        self.assertIn("rt3", sql)

        # Verify eq params
        # params[0] = collapsed eq {'name': 'John', 'status': 'active'}
        self.assertEqual(params[0].obj, {'name': 'John', 'status': 'active'})

    def test_unique_aliases_no_collision(self):
        """Each nested EXISTS gets a unique alias."""
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = CompositeQuery({
            'company_id': RelOperator(CompositeQuery({
                'name': EqOperator('Acme'),
                'country_id': RelOperator(CompositeQuery({
                    'code': EqOperator('US'),
                })),
            })),
        })

        sql, params = compiler.compile(query)

        # rt1 = companies, rt2 = countries — no collision
        self.assertIn("rt1", sql)
        self.assertIn("rt2", sql)
        # rt1 should reference companies, rt2 should reference countries
        self.assertRegex(sql, r"FROM companies rt1")
        self.assertRegex(sql, r"FROM countries rt2")

    def test_or_both_branches_reference_same_table(self):
        """$or at level 2 where both branches are $rel to level 3."""
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = CompositeQuery({
            'company_id': RelOperator(CompositeQuery({
                'country_id': OrOperator((
                    RelOperator(CompositeQuery({
                        'code': EqOperator('US'),
                    })),
                    RelOperator(CompositeQuery({
                        'code': EqOperator('UK'),
                    })),
                )),
            })),
        })

        sql, params = compiler.compile(query)

        # Two countries EXISTS inside OR, each with unique alias
        self.assertEqual(sql.count("FROM countries"), 2)
        # Both should be inside OR
        self.assertIn(" OR ", sql)


if __name__ == '__main__':
    unittest.main()
