"""Tests for PgQueryCompiler."""
import unittest

from ascetic_ddd.faker.domain.query.operators import (
    EqOperator, ComparisonOperator, InOperator, IsNullOperator,
    NotOperator, AnyElementOperator, AllElementsOperator, LenOperator,
    AndOperator, OrOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.infrastructure.query.pg_query_compiler import PgQueryCompiler, RelationInfo, IRelationResolver


class StubRelationResolver(IRelationResolver):
    """Test stub: resolves field names to table/pk info via a dict."""

    def __init__(self, relations: dict[str | None, tuple[str, str, 'StubRelationResolver | None']]):
        # relations: {field: (table, pk_field, nested_resolver)}
        self._relations = relations

    def resolve(self, field: str | None) -> RelationInfo | None:
        info = self._relations.get(field)
        if info is None:
            return None
        return RelationInfo(table=info[0], pk_field=info[1], nested_resolver=info[2])

    def descend(self, field: str) -> 'StubRelationResolver | None':
        return None


class DescendableStubRelationResolver(IRelationResolver):
    """Test stub with descend support for nested composite resolution."""

    def __init__(
            self,
            relations: dict[str | None, tuple[str, str, 'IRelationResolver | None']],
            children: dict[str, 'IRelationResolver'] | None = None,
    ):
        self._relations = relations
        self._children = children or {}

    def resolve(self, field: str | None) -> RelationInfo | None:
        info = self._relations.get(field)
        if info is None:
            return None
        return RelationInfo(table=info[0], pk_field=info[1], nested_resolver=info[2])

    def descend(self, field: str) -> 'IRelationResolver | None':
        return self._children.get(field)


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


class TestVisitIsNull(unittest.TestCase):

    def test_is_null_true_bare(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(IsNullOperator(True))
        self.assertEqual(sql, "value IS NULL")
        self.assertEqual(params, ())

    def test_is_null_false_bare(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(IsNullOperator(False))
        self.assertEqual(sql, "value IS NOT NULL")
        self.assertEqual(params, ())

    def test_is_null_in_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'name': IsNullOperator(True),
        }))
        self.assertEqual(sql, "value->'name' IS NULL")
        self.assertEqual(params, ())

    def test_is_null_false_in_composite(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'name': IsNullOperator(False),
        }))
        self.assertEqual(sql, "value->'name' IS NOT NULL")
        self.assertEqual(params, ())

    def test_is_null_mixed_with_eq(self):
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': EqOperator('active'),
            'deleted_at': IsNullOperator(True),
        }))
        self.assertIn("IS NULL", sql)
        self.assertIn("@>", sql)


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


class TestVisitNot(unittest.TestCase):

    def test_not_bare_eq(self):
        """NOT wraps the inner expression."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(NotOperator(EqOperator('deleted')))
        self.assertEqual(sql, "NOT (value @> %s)")
        self.assertEqual(params[0].obj, 'deleted')

    def test_not_in_composite(self):
        """$not inside CompositeQuery."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': NotOperator(EqOperator('deleted')),
        }))
        self.assertEqual(sql, "NOT (value @> %s)")
        self.assertEqual(params[0].obj, {'status': 'deleted'})

    def test_not_with_comparison(self):
        """$not wrapping $gt."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'age': NotOperator(ComparisonOperator('$gt', 65)),
        }))
        self.assertEqual(sql, "NOT (value->'age' > %s)")
        self.assertEqual(params, (65,))

    def test_not_mixed_with_eq(self):
        """$not alongside regular $eq field."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'status': EqOperator('active'),
            'role': NotOperator(EqOperator('admin')),
        }))
        self.assertIn("value @> %s", sql)
        self.assertIn("NOT (value @> %s)", sql)


class TestVisitAnyElement(unittest.TestCase):

    def test_any_bare(self):
        """$any generates EXISTS + jsonb_array_elements."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(
            AnyElementOperator(CompositeQuery({'status': EqOperator('shipped')}))
        )
        self.assertIn("EXISTS", sql)
        self.assertIn("jsonb_array_elements", sql)
        self.assertIn("rt1", sql)

    def test_any_in_composite(self):
        """$any inside CompositeQuery."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'items': AnyElementOperator(CompositeQuery({
                'status': EqOperator('shipped'),
            }))
        }))
        self.assertIn("EXISTS", sql)
        self.assertIn("jsonb_array_elements(value->'items')", sql)
        self.assertIn("rt1", sql)
        self.assertEqual(params[0].obj, {'status': 'shipped'})

    def test_any_with_comparison(self):
        """$any with $gt inside."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'prices': AnyElementOperator(CompositeQuery({
                'amount': ComparisonOperator('$gt', 100),
            }))
        }))
        self.assertIn("EXISTS", sql)
        self.assertIn("jsonb_array_elements(value->'prices')", sql)
        self.assertIn("> %s", sql)
        self.assertEqual(params[0], 100)

    def test_nested_any(self):
        """Nested $any: items -> tags, two levels of jsonb_array_elements."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'items': AnyElementOperator(CompositeQuery({
                'tags': AnyElementOperator(EqOperator('urgent')),
            }))
        }))
        self.assertIn("jsonb_array_elements(value->'items')", sql)
        self.assertIn("rt1", sql)
        self.assertIn("jsonb_array_elements(rt1->'tags')", sql)
        self.assertIn("rt2", sql)
        # Two nested EXISTS
        self.assertEqual(sql.count("EXISTS"), 2)
        self.assertEqual(params[0].obj, 'urgent')


class TestVisitAllElements(unittest.TestCase):

    def test_all_bare(self):
        """$all generates NOT EXISTS + jsonb_array_elements + NOT."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(
            AllElementsOperator(CompositeQuery({'status': EqOperator('active')}))
        )
        self.assertIn("NOT EXISTS", sql)
        self.assertIn("jsonb_array_elements", sql)
        self.assertIn("WHERE NOT", sql)

    def test_all_in_composite(self):
        """$all inside CompositeQuery."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'items': AllElementsOperator(CompositeQuery({
                'status': EqOperator('active'),
            }))
        }))
        self.assertIn("NOT EXISTS", sql)
        self.assertIn("jsonb_array_elements(value->'items')", sql)
        self.assertIn("WHERE NOT", sql)
        self.assertEqual(params[0].obj, {'status': 'active'})


class TestVisitLen(unittest.TestCase):

    def test_len_gt(self):
        """$len with $gt."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'items': LenOperator(ComparisonOperator('$gt', 2)),
        }))
        self.assertEqual(sql, "jsonb_array_length(value->'items') > %s")
        self.assertEqual(params, (2,))

    def test_len_eq(self):
        """$len with $eq."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'items': LenOperator(EqOperator(0)),
        }))
        self.assertEqual(sql, "jsonb_array_length(value->'items') = %s")
        self.assertEqual(params, (0,))

    def test_len_gte(self):
        """$len with $gte."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'items': LenOperator(ComparisonOperator('$gte', 1)),
        }))
        self.assertEqual(sql, "jsonb_array_length(value->'items') >= %s")
        self.assertEqual(params, (1,))

    def test_len_ne(self):
        """$len with $ne."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'items': LenOperator(ComparisonOperator('$ne', 0)),
        }))
        self.assertEqual(sql, "jsonb_array_length(value->'items') != %s")
        self.assertEqual(params, (0,))

    def test_len_bare(self):
        """$len without field context."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(LenOperator(ComparisonOperator('$gt', 2)))
        self.assertEqual(sql, "jsonb_array_length(value) > %s")
        self.assertEqual(params, (2,))


class TestCombinedNewOperators(unittest.TestCase):

    def test_any_and_len_at_same_level(self):
        """$any + $len at same level (implicit AND)."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'items': AndOperator((
                AnyElementOperator(CompositeQuery({
                    'price': ComparisonOperator('$gt', 100),
                })),
                LenOperator(ComparisonOperator('$gte', 1)),
            ))
        }))
        self.assertIn("EXISTS", sql)
        self.assertIn("jsonb_array_length", sql)
        self.assertIn("AND", sql)

    def test_not_with_len(self):
        """$not wrapping $len."""
        compiler = PgQueryCompiler()
        sql, params = compiler.compile(CompositeQuery({
            'items': NotOperator(LenOperator(ComparisonOperator('$gt', 5))),
        }))
        self.assertIn("NOT (", sql)
        self.assertIn("jsonb_array_length", sql)


class TestRootWithCascadingRelations(unittest.TestCase):
    """Root-level $rel + Three-table cascade: ID -> employees -> companies -> countries.

    Simulates ReferenceProvider distributor scenario where distributor stores IDs
    and top-level $rel generates EXISTS subquery via resolver(field=None).
    """

    def _make_resolvers(self):
        country_resolver = StubRelationResolver({})
        company_resolver = StubRelationResolver({
            'country_id': ('countries', 'value_id', country_resolver),
        })
        employee_resolver = StubRelationResolver({
            'company_id': ('companies', 'value_id', company_resolver),
        })
        # Root resolver: field=None resolves to employees table
        root_resolver = StubRelationResolver({
            None: ('employees', 'value_id', employee_resolver),
        })
        return root_resolver

    def test_root_rel_simple(self):
        """Top-level $rel should generate EXISTS subquery."""
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = RelOperator(CompositeQuery({
            'name': EqOperator('John'),
            'status': EqOperator('active'),
        }))

        sql, params = compiler.compile(query)

        # EXISTS against employees table
        self.assertIn("EXISTS (SELECT 1 FROM employees", sql)
        # Join on value directly (not value->'field')
        self.assertIn("rt1.value_id = value)", sql)

    def test_root_rel_three_table_cascade(self):
        """Root $rel with three-table cascade."""
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = RelOperator(CompositeQuery({
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
        }))

        sql, params = compiler.compile(query)

        # Root level: EXISTS for employees
        self.assertIn("EXISTS (SELECT 1 FROM employees", sql)
        # Root join: value directly (top-level)
        self.assertIn("rt1.value_id = value)", sql)

        # Companies level: nested EXISTS
        self.assertIn("EXISTS (SELECT 1 FROM companies", sql)

        # Countries level: two nested EXISTS inside OR
        self.assertEqual(sql.count("EXISTS (SELECT 1 FROM countries"), 2)

        # All aliases must be unique (rt1, rt2, rt3, rt4)
        self.assertIn("rt1", sql)
        self.assertIn("rt2", sql)
        self.assertIn("rt3", sql)
        self.assertIn("rt4", sql)

    def test_root_rel_unique_aliases(self):
        """Each nested EXISTS gets a unique alias including root."""
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = RelOperator(CompositeQuery({
            'company_id': RelOperator(CompositeQuery({
                'name': EqOperator('Acme'),
                'country_id': RelOperator(CompositeQuery({
                    'code': EqOperator('US'),
                })),
            })),
        }))

        sql, params = compiler.compile(query)

        # rt1 = employees, rt2 = companies, rt3 = countries
        self.assertRegex(sql, r"FROM employees rt1")
        self.assertRegex(sql, r"FROM companies rt2")
        self.assertRegex(sql, r"FROM countries rt3")

    def test_root_rel_or_both_branches_reference_same_table(self):
        """Root $rel with $or where both branches are $rel to same table."""
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = RelOperator(CompositeQuery({
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
        }))

        sql, params = compiler.compile(query)

        # Root EXISTS for employees
        self.assertIn("EXISTS (SELECT 1 FROM employees", sql)
        # Two countries EXISTS inside OR
        self.assertEqual(sql.count("FROM countries"), 2)
        self.assertIn(" OR ", sql)


class TestNestedCompositeDescend(unittest.TestCase):
    """Nested composite $rel via descend: ResumeId -> UserId -> Tenant.

    ResumeId = {user_id: {tenant_id: FK, local_user_id: int}, local_resume_id: int}
    Query asks for tenant with specific name via $rel inside nested composite.
    """

    def _make_resolvers(self):
        tenant_resolver = StubRelationResolver({})

        # UserIdProvider level: tenant_id -> tenants table
        user_id_resolver = DescendableStubRelationResolver(
            relations={'tenant_id': ('tenants', 'value_id', tenant_resolver)},
        )

        # ResumeIdProvider level: descend('user_id') -> user_id_resolver
        resume_id_resolver = DescendableStubRelationResolver(
            relations={},
            children={'user_id': user_id_resolver},
        )
        return resume_id_resolver

    def test_nested_descend_rel(self):
        """$rel inside nested composite should generate EXISTS via descend."""
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = CompositeQuery({
            'user_id': CompositeQuery({
                'tenant_id': RelOperator(CompositeQuery({
                    'name': EqOperator('TenantA'),
                })),
            }),
        })

        sql, params = compiler.compile(query)

        # Should generate EXISTS subquery against tenants table
        self.assertIn("EXISTS (SELECT 1 FROM tenants", sql)
        # Join expression should use nested path value->'user_id'->'tenant_id'
        self.assertIn("value->'user_id'->'tenant_id'", sql)

    def test_nested_descend_rel_with_eq(self):
        """$rel + $eq inside nested composite."""
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = CompositeQuery({
            'user_id': CompositeQuery({
                'local_user_id': EqOperator(42),
                'tenant_id': RelOperator(CompositeQuery({
                    'name': EqOperator('TenantA'),
                })),
            }),
        })

        sql, params = compiler.compile(query)

        # Both @> for collapsed eq and EXISTS for $rel
        self.assertIn("@> %s", sql)
        self.assertIn("EXISTS (SELECT 1 FROM tenants", sql)
        # Collapsed eq should contain nested path
        eq_param = next(p for p in params if hasattr(p, 'obj') and isinstance(p.obj, dict))
        self.assertEqual(eq_param.obj, {'user_id': {'local_user_id': 42}})

    def test_nested_descend_rel_with_top_level_eq(self):
        """$rel inside nested composite alongside top-level $eq."""
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = CompositeQuery({
            'local_resume_id': EqOperator(7),
            'user_id': CompositeQuery({
                'tenant_id': RelOperator(CompositeQuery({
                    'name': EqOperator('TenantA'),
                })),
            }),
        })

        sql, params = compiler.compile(query)

        self.assertIn("@> %s", sql)
        self.assertIn("EXISTS (SELECT 1 FROM tenants", sql)
        eq_param = next(p for p in params if hasattr(p, 'obj') and isinstance(p.obj, dict))
        self.assertEqual(eq_param.obj, {'local_resume_id': 7})

    def test_nested_descend_rel_with_comparison(self):
        """$rel with comparison inside nested composite."""
        resolver = self._make_resolvers()
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = CompositeQuery({
            'user_id': CompositeQuery({
                'tenant_id': RelOperator(CompositeQuery({
                    'priority': ComparisonOperator('$gte', 5),
                })),
            }),
        })

        sql, params = compiler.compile(query)

        self.assertIn("EXISTS (SELECT 1 FROM tenants", sql)
        self.assertIn(">= %s", sql)

    def test_no_descend_without_resolver(self):
        """Without resolver, $rel in nested composite raises TypeError."""
        compiler = PgQueryCompiler()

        query = CompositeQuery({
            'user_id': CompositeQuery({
                'tenant_id': RelOperator(CompositeQuery({
                    'name': EqOperator('TenantA'),
                })),
            }),
        })

        with self.assertRaises(TypeError):
            compiler.compile(query)

    def test_nested_descend_no_child(self):
        """descend returns None for non-composite fields — $rel raises TypeError."""
        # Resolver with no children for 'other_field'
        resolver = DescendableStubRelationResolver(
            relations={},
            children={},
        )
        compiler = PgQueryCompiler(relation_resolver=resolver)

        query = CompositeQuery({
            'other_field': CompositeQuery({
                'fk': RelOperator(CompositeQuery({
                    'name': EqOperator('X'),
                })),
            }),
        })

        # descend returns None, so resolver stays at top level
        # top-level resolver can't resolve 'fk' -> fallback to _to_dict
        sql, params = compiler.compile(query)
        # _compile_rel_field fallback: non-reference field with _to_dict
        self.assertIn("@> %s", sql)


if __name__ == '__main__':
    unittest.main()
