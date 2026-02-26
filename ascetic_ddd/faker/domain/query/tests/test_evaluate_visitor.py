"""Tests for EvaluateWalker."""
import unittest
from unittest import IsolatedAsyncioTestCase

from ascetic_ddd.faker.domain.query.evaluate_visitor import (
    EvaluateWalker, EvaluateVisitor, IObjectResolver
)
from ascetic_ddd.faker.domain.query.operators import (
    EqOperator, ComparisonOperator, InOperator, IsNullOperator, AndOperator,
    OrOperator, RelOperator, CompositeQuery
)
from ascetic_ddd.faker.domain.query.parser import QueryParser


# =============================================================================
# Test Fixtures - Three-level hierarchy: Employee -> Company -> Country
# =============================================================================

class MockSession:
    """Mock session for testing."""
    pass


class StubObjectResolver(IObjectResolver):
    """Test stub: resolves field names to foreign object state via a dict."""

    def __init__(self, relations: dict[str, tuple[dict, 'StubObjectResolver | None']]):
        # relations: {field: (storage_dict, nested_resolver)}
        # storage_dict: {fk_value: state_dict}
        self._relations = relations

    async def resolve(self, session, field, fk_value):
        info = self._relations.get(field)
        if info is None:
            return None, None
        storage, nested = info
        state = storage.get(fk_value)
        if state is None:
            return None, None
        return state, nested


# =============================================================================
# Tests for EvaluateWalker - Basic (no resolver)
# =============================================================================

class EvaluateWalkerBasicTestCase(IsolatedAsyncioTestCase):
    """Basic tests for EvaluateWalker without object resolver."""

    def setUp(self):
        self.visitor = EvaluateWalker()
        self.session = MockSession()

    async def test_eq_matches(self):
        """EqOperator should match equal value."""
        self.assertTrue(
            await self.visitor.evaluate(self.session, EqOperator(42), 42)
        )

    async def test_eq_not_matches(self):
        """EqOperator should not match different value."""
        self.assertFalse(
            await self.visitor.evaluate(self.session, EqOperator(42), 99)
        )

    async def test_eq_none(self):
        """EqOperator(None) should match None."""
        self.assertTrue(
            await self.visitor.evaluate(self.session, EqOperator(None), None)
        )

    async def test_eq_string(self):
        """EqOperator should match string value."""
        self.assertTrue(
            await self.visitor.evaluate(self.session, EqOperator('active'), 'active')
        )

    async def test_comparison_ne(self):
        """$ne should match when values differ."""
        op = ComparisonOperator('$ne', 'deleted')
        self.assertTrue(await self.visitor.evaluate(self.session, op, 'active'))
        self.assertFalse(await self.visitor.evaluate(self.session, op, 'deleted'))

    async def test_comparison_gt(self):
        """$gt should match when actual > expected."""
        op = ComparisonOperator('$gt', 10)
        self.assertTrue(await self.visitor.evaluate(self.session, op, 15))
        self.assertFalse(await self.visitor.evaluate(self.session, op, 10))
        self.assertFalse(await self.visitor.evaluate(self.session, op, 5))

    async def test_comparison_gte(self):
        """$gte should match when actual >= expected."""
        op = ComparisonOperator('$gte', 10)
        self.assertTrue(await self.visitor.evaluate(self.session, op, 15))
        self.assertTrue(await self.visitor.evaluate(self.session, op, 10))
        self.assertFalse(await self.visitor.evaluate(self.session, op, 5))

    async def test_comparison_lt(self):
        """$lt should match when actual < expected."""
        op = ComparisonOperator('$lt', 10)
        self.assertTrue(await self.visitor.evaluate(self.session, op, 5))
        self.assertFalse(await self.visitor.evaluate(self.session, op, 10))
        self.assertFalse(await self.visitor.evaluate(self.session, op, 15))

    async def test_comparison_lte(self):
        """$lte should match when actual <= expected."""
        op = ComparisonOperator('$lte', 10)
        self.assertTrue(await self.visitor.evaluate(self.session, op, 5))
        self.assertTrue(await self.visitor.evaluate(self.session, op, 10))
        self.assertFalse(await self.visitor.evaluate(self.session, op, 15))

    async def test_in_operator_matches(self):
        """$in should match when value is in the list."""
        op = InOperator(('active', 'pending'))
        self.assertTrue(await self.visitor.evaluate(self.session, op, 'active'))
        self.assertTrue(await self.visitor.evaluate(self.session, op, 'pending'))

    async def test_in_operator_not_matches(self):
        """$in should not match when value is not in the list."""
        op = InOperator(('active', 'pending'))
        self.assertFalse(await self.visitor.evaluate(self.session, op, 'deleted'))

    async def test_is_null_true_matches_none(self):
        """IsNullOperator(True) should match None."""
        op = IsNullOperator(True)
        self.assertTrue(await self.visitor.evaluate(self.session, op, None))

    async def test_is_null_true_not_matches_value(self):
        """IsNullOperator(True) should not match non-None."""
        op = IsNullOperator(True)
        self.assertFalse(await self.visitor.evaluate(self.session, op, 42))

    async def test_is_null_false_matches_value(self):
        """IsNullOperator(False) should match non-None."""
        op = IsNullOperator(False)
        self.assertTrue(await self.visitor.evaluate(self.session, op, 42))

    async def test_is_null_false_not_matches_none(self):
        """IsNullOperator(False) should not match None."""
        op = IsNullOperator(False)
        self.assertFalse(await self.visitor.evaluate(self.session, op, None))

    async def test_is_null_in_composite(self):
        """IsNullOperator in CompositeQuery."""
        query = CompositeQuery({'name': IsNullOperator(True)})
        self.assertTrue(await self.visitor.evaluate(
            self.session, query, {'name': None}
        ))
        self.assertFalse(await self.visitor.evaluate(
            self.session, query, {'name': 'Alice'}
        ))

    async def test_and_operator_all_true(self):
        """AndOperator should match when all operands match."""
        op = AndOperator((
            ComparisonOperator('$gt', 5),
            ComparisonOperator('$lt', 10),
        ))
        self.assertTrue(await self.visitor.evaluate(self.session, op, 7))

    async def test_and_operator_one_false(self):
        """AndOperator should not match when any operand fails."""
        op = AndOperator((
            ComparisonOperator('$gt', 5),
            ComparisonOperator('$lt', 10),
        ))
        self.assertFalse(await self.visitor.evaluate(self.session, op, 12))

    async def test_or_operator_one_true(self):
        """OrOperator should match when any operand matches."""
        op = OrOperator((
            EqOperator('active'),
            EqOperator('pending'),
        ))
        self.assertTrue(await self.visitor.evaluate(self.session, op, 'pending'))

    async def test_or_operator_none_true(self):
        """OrOperator should not match when no operand matches."""
        op = OrOperator((
            EqOperator('active'),
            EqOperator('pending'),
        ))
        self.assertFalse(await self.visitor.evaluate(self.session, op, 'deleted'))

    async def test_composite_matches(self):
        """CompositeQuery should match when all fields match."""
        query = CompositeQuery({
            'status': EqOperator('active'),
            'name': EqOperator('Alice'),
        })
        state = {'status': 'active', 'name': 'Alice', 'extra': 'ignored'}
        self.assertTrue(await self.visitor.evaluate(self.session, query, state))

    async def test_composite_not_matches(self):
        """CompositeQuery should not match when any field fails."""
        query = CompositeQuery({
            'status': EqOperator('active'),
            'name': EqOperator('Alice'),
        })
        state = {'status': 'inactive', 'name': 'Alice'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, state))

    async def test_composite_non_dict_state(self):
        """CompositeQuery should return False for non-dict state."""
        query = CompositeQuery({'status': EqOperator('active')})
        self.assertFalse(await self.visitor.evaluate(self.session, query, 42))

    async def test_nested_composite_without_resolver(self):
        """Nested CompositeQuery should match nested dict state."""
        query = CompositeQuery({
            'address': CompositeQuery({
                'city': EqOperator('Moscow'),
            }),
        })
        state = {'address': {'city': 'Moscow', 'street': 'Main'}}
        self.assertTrue(await self.visitor.evaluate(self.session, query, state))

        state_wrong = {'address': {'city': 'London'}}
        self.assertFalse(await self.visitor.evaluate(self.session, query, state_wrong))

    async def test_composite_with_comparison(self):
        """CompositeQuery with comparison operators."""
        query = CompositeQuery({
            'name': EqOperator('John'),
            'age': AndOperator((
                ComparisonOperator('$gte', 18),
                ComparisonOperator('$lt', 65),
            )),
        })
        state = {'name': 'John', 'age': 30}
        self.assertTrue(await self.visitor.evaluate(self.session, query, state))

        state_young = {'name': 'John', 'age': 15}
        self.assertFalse(await self.visitor.evaluate(self.session, query, state_young))

    async def test_composite_with_or(self):
        """CompositeQuery with $or operator."""
        query = CompositeQuery({
            'status': OrOperator((
                EqOperator('active'),
                EqOperator('pending'),
            )),
        })
        self.assertTrue(
            await self.visitor.evaluate(self.session, query, {'status': 'active'})
        )
        self.assertTrue(
            await self.visitor.evaluate(self.session, query, {'status': 'pending'})
        )
        self.assertFalse(
            await self.visitor.evaluate(self.session, query, {'status': 'deleted'})
        )

    async def test_composite_with_in(self):
        """CompositeQuery with $in operator."""
        query = CompositeQuery({
            'status': InOperator(('active', 'pending')),
        })
        self.assertTrue(
            await self.visitor.evaluate(self.session, query, {'status': 'active'})
        )
        self.assertFalse(
            await self.visitor.evaluate(self.session, query, {'status': 'deleted'})
        )

    async def test_parsed_simple_pattern(self):
        """Parsed query should work with evaluate."""
        query = QueryParser().parse({'status': 'active'})
        self.assertTrue(
            await self.visitor.evaluate(
                self.session, query, {'status': 'active', 'name': 'test'}
            )
        )
        self.assertFalse(
            await self.visitor.evaluate(
                self.session, query, {'status': 'inactive', 'name': 'test'}
            )
        )

    async def test_rel_without_resolver_delegates_to_inner(self):
        """RelOperator without field context delegates to inner query."""
        query = RelOperator(CompositeQuery({
            'name': EqOperator('Active'),
        }))
        state = {'name': 'Active'}
        self.assertTrue(await self.visitor.evaluate(self.session, query, state))

        state_wrong = {'name': 'Inactive'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, state_wrong))


# =============================================================================
# Tests for EvaluateWalker - Nested Lookup (2 levels)
# =============================================================================

class EvaluateWalkerNestedLookupTestCase(IsolatedAsyncioTestCase):
    """Tests for nested lookup with object resolver (User -> Status)."""

    def setUp(self):
        self.session = MockSession()

        # Status storage: {status_id: status_state}
        self.status_storage = {
            'active': {'id': 'active', 'name': 'Active'},
            'inactive': {'id': 'inactive', 'name': 'Inactive'},
        }

        # Resolver: status_id field resolves to status storage
        status_resolver = StubObjectResolver({})
        self.resolver = StubObjectResolver({
            'status_id': (self.status_storage, status_resolver),
        })
        self.visitor = EvaluateWalker(self.resolver)

    async def test_nested_lookup_matches(self):
        """Nested lookup should match when foreign object satisfies criteria."""
        query = CompositeQuery({
            'status_id': RelOperator(CompositeQuery({
                'name': EqOperator('Active'),
            })),
        })
        # User with active status
        state = {'id': 1, 'status_id': 'active', 'name': 'Alice'}
        self.assertTrue(await self.visitor.evaluate(self.session, query, state))

    async def test_nested_lookup_not_matches(self):
        """Nested lookup should not match when foreign object doesn't satisfy criteria."""
        query = CompositeQuery({
            'status_id': RelOperator(CompositeQuery({
                'name': EqOperator('Active'),
            })),
        })
        # User with inactive status
        state = {'id': 2, 'status_id': 'inactive', 'name': 'Bob'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, state))

    async def test_nested_lookup_fk_is_none(self):
        """Nested lookup should return False when FK value is None."""
        query = CompositeQuery({
            'status_id': RelOperator(CompositeQuery({
                'name': EqOperator('Active'),
            })),
        })
        state = {'id': 3, 'status_id': None, 'name': 'Charlie'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, state))

    async def test_nested_lookup_foreign_not_found(self):
        """Nested lookup should return False when foreign object not found."""
        query = CompositeQuery({
            'status_id': RelOperator(CompositeQuery({
                'name': EqOperator('Active'),
            })),
        })
        state = {'id': 4, 'status_id': 'unknown', 'name': 'Dave'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, state))

    async def test_simple_value_with_nested_lookup(self):
        """Simple value comparison should work alongside nested lookup."""
        query = CompositeQuery({
            'name': EqOperator('Alice'),
            'status_id': RelOperator(CompositeQuery({
                'name': EqOperator('Active'),
            })),
        })
        # Alice with active status - matches both
        state_alice = {'id': 1, 'status_id': 'active', 'name': 'Alice'}
        self.assertTrue(await self.visitor.evaluate(self.session, query, state_alice))

        # Bob with inactive status - doesn't match name
        state_bob = {'id': 2, 'status_id': 'inactive', 'name': 'Bob'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, state_bob))

    async def test_nested_lookup_with_comparison(self):
        """Nested lookup with comparison operator on foreign field."""
        # Add statuses with priority
        self.status_storage['high'] = {'id': 'high', 'name': 'High', 'priority': 10}
        self.status_storage['low'] = {'id': 'low', 'name': 'Low', 'priority': 1}

        query = CompositeQuery({
            'status_id': RelOperator(CompositeQuery({
                'priority': ComparisonOperator('$gte', 5),
            })),
        })

        state_high = {'id': 1, 'status_id': 'high', 'name': 'Alice'}
        self.assertTrue(await self.visitor.evaluate(self.session, query, state_high))

        state_low = {'id': 2, 'status_id': 'low', 'name': 'Bob'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, state_low))

    async def test_non_relation_field_with_resolver(self):
        """Non-relation field should use regular evaluation even with resolver."""
        query = CompositeQuery({
            'name': EqOperator('Alice'),
        })
        state = {'id': 1, 'status_id': 'active', 'name': 'Alice'}
        self.assertTrue(await self.visitor.evaluate(self.session, query, state))


# =============================================================================
# Tests for EvaluateWalker - Three Table Cascade
# =============================================================================

class EvaluateWalkerThreeTableCascadeTestCase(IsolatedAsyncioTestCase):
    """Three-table cascade: Employee -> Company -> Country."""

    def setUp(self):
        self.session = MockSession()

        # Country storage
        self.country_storage = {
            'US': {'id': 'US', 'code': 'US', 'continent': 'America'},
            'UK': {'id': 'UK', 'code': 'UK', 'continent': 'Europe'},
            'JP': {'id': 'JP', 'code': 'JP', 'continent': 'Asia'},
        }

        # Company storage
        self.company_storage = {
            1: {
                'id': 1, 'country_id': 'US', 'name': 'Acme',
                'type': 'tech', 'revenue': 2000000,
            },
            2: {
                'id': 2, 'country_id': 'UK', 'name': 'BritCo',
                'type': 'finance', 'revenue': 500000,
            },
            3: {
                'id': 3, 'country_id': 'JP', 'name': 'TokyoTech',
                'type': 'tech', 'revenue': 800000,
            },
        }

        # Build resolvers (Country has no FK fields)
        country_resolver = StubObjectResolver({})
        company_resolver = StubObjectResolver({
            'country_id': (self.country_storage, country_resolver),
        })
        self.resolver = StubObjectResolver({
            'company_id': (self.company_storage, company_resolver),
        })
        self.visitor = EvaluateWalker(self.resolver)

    async def test_three_table_cascade_matches(self):
        """Three-level cascade should match when all levels satisfy criteria."""
        # Employee -> Company(tech) -> Country(US)
        query = CompositeQuery({
            'name': EqOperator('John'),
            'status': EqOperator('active'),
            'company_id': RelOperator(CompositeQuery({
                'type': EqOperator('tech'),
                'country_id': RelOperator(CompositeQuery({
                    'code': EqOperator('US'),
                })),
            })),
        })

        employee = {
            'id': 1, 'company_id': 1, 'name': 'John',
            'age': 30, 'status': 'active',
        }
        self.assertTrue(await self.visitor.evaluate(self.session, query, employee))

    async def test_three_table_cascade_not_matches_middle(self):
        """Cascade should fail when middle level doesn't match."""
        # Employee -> Company(tech) but BritCo is finance
        query = CompositeQuery({
            'company_id': RelOperator(CompositeQuery({
                'type': EqOperator('tech'),
            })),
        })

        employee = {'id': 2, 'company_id': 2, 'name': 'Jane', 'age': 25, 'status': 'active'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, employee))

    async def test_three_table_cascade_not_matches_deepest(self):
        """Cascade should fail when deepest level doesn't match."""
        # Employee -> Company(Acme, US) but query asks for UK
        query = CompositeQuery({
            'company_id': RelOperator(CompositeQuery({
                'country_id': RelOperator(CompositeQuery({
                    'code': EqOperator('UK'),
                })),
            })),
        })

        # Employee at Acme (US) — should fail
        employee = {'id': 1, 'company_id': 1, 'name': 'John', 'age': 30, 'status': 'active'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, employee))

        # Employee at BritCo (UK) — should match
        employee_uk = {'id': 2, 'company_id': 2, 'name': 'Jane', 'age': 25, 'status': 'active'}
        self.assertTrue(await self.visitor.evaluate(self.session, query, employee_uk))

    async def test_or_in_cascade(self):
        """$or at company level with two $rel branches to country."""
        # Companies in US or UK
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

        # Employee at Acme (US) — matches
        employee_us = {'id': 1, 'company_id': 1, 'name': 'John', 'age': 30, 'status': 'active'}
        self.assertTrue(await self.visitor.evaluate(self.session, query, employee_us))

        # Employee at BritCo (UK) — matches
        employee_uk = {'id': 2, 'company_id': 2, 'name': 'Jane', 'age': 25, 'status': 'active'}
        self.assertTrue(await self.visitor.evaluate(self.session, query, employee_uk))

        # Employee at TokyoTech (JP) — doesn't match
        employee_jp = {'id': 3, 'company_id': 3, 'name': 'Yuki', 'age': 28, 'status': 'active'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, employee_jp))

    async def test_cascade_with_all_operators(self):
        """Three-table cascade with mixed operators at each level."""
        # Level 1 (employees): $eq + $gt
        # Level 2 (companies): $eq + $gte
        # Level 3 (countries): $eq
        query = CompositeQuery({
            'name': EqOperator('John'),
            'age': ComparisonOperator('$gt', 25),
            'company_id': RelOperator(CompositeQuery({
                'type': EqOperator('tech'),
                'revenue': ComparisonOperator('$gte', 1000000),
                'country_id': RelOperator(CompositeQuery({
                    'code': EqOperator('US'),
                })),
            })),
        })

        # John, age 30, Acme (tech, revenue 2M, US) — all match
        employee = {'id': 1, 'company_id': 1, 'name': 'John', 'age': 30, 'status': 'active'}
        self.assertTrue(await self.visitor.evaluate(self.session, query, employee))

        # John, age 30, TokyoTech (tech, revenue 800K, JP) — revenue too low
        employee2 = {'id': 4, 'company_id': 3, 'name': 'John', 'age': 30, 'status': 'active'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, employee2))

    async def test_cascade_company_not_found(self):
        """Cascade should fail when FK points to non-existent object."""
        query = CompositeQuery({
            'company_id': RelOperator(CompositeQuery({
                'type': EqOperator('tech'),
            })),
        })

        employee = {'id': 5, 'company_id': 999, 'name': 'Ghost', 'age': 0, 'status': 'unknown'}
        self.assertFalse(await self.visitor.evaluate(self.session, query, employee))


# =============================================================================
# Tests for EvaluateVisitor - Basic (no resolver)
# =============================================================================

class EvaluateVisitorBasicTestCase(IsolatedAsyncioTestCase):
    """Basic tests for EvaluateVisitor without object resolver."""

    def setUp(self):
        self.session = MockSession()

    def _eval(self, state, query, resolver=None, _field_context=None):
        return query.accept(EvaluateVisitor(state, self.session, resolver, _field_context))

    async def test_eq_matches(self):
        self.assertTrue(await self._eval(42, EqOperator(42)))

    async def test_eq_not_matches(self):
        self.assertFalse(await self._eval(99, EqOperator(42)))

    async def test_eq_none(self):
        self.assertTrue(await self._eval(None, EqOperator(None)))

    async def test_eq_string(self):
        self.assertTrue(await self._eval('active', EqOperator('active')))

    async def test_comparison_ne(self):
        op = ComparisonOperator('$ne', 'deleted')
        self.assertTrue(await self._eval('active', op))
        self.assertFalse(await self._eval('deleted', op))

    async def test_comparison_gt(self):
        op = ComparisonOperator('$gt', 10)
        self.assertTrue(await self._eval(15, op))
        self.assertFalse(await self._eval(10, op))
        self.assertFalse(await self._eval(5, op))

    async def test_comparison_gte(self):
        op = ComparisonOperator('$gte', 10)
        self.assertTrue(await self._eval(15, op))
        self.assertTrue(await self._eval(10, op))
        self.assertFalse(await self._eval(5, op))

    async def test_comparison_lt(self):
        op = ComparisonOperator('$lt', 10)
        self.assertTrue(await self._eval(5, op))
        self.assertFalse(await self._eval(10, op))
        self.assertFalse(await self._eval(15, op))

    async def test_comparison_lte(self):
        op = ComparisonOperator('$lte', 10)
        self.assertTrue(await self._eval(5, op))
        self.assertTrue(await self._eval(10, op))
        self.assertFalse(await self._eval(15, op))

    async def test_in_operator_matches(self):
        op = InOperator(('active', 'pending'))
        self.assertTrue(await self._eval('active', op))
        self.assertTrue(await self._eval('pending', op))

    async def test_in_operator_not_matches(self):
        op = InOperator(('active', 'pending'))
        self.assertFalse(await self._eval('deleted', op))

    async def test_is_null_true_matches_none(self):
        self.assertTrue(await self._eval(None, IsNullOperator(True)))

    async def test_is_null_true_not_matches_value(self):
        self.assertFalse(await self._eval(42, IsNullOperator(True)))

    async def test_is_null_false_matches_value(self):
        self.assertTrue(await self._eval(42, IsNullOperator(False)))

    async def test_is_null_false_not_matches_none(self):
        self.assertFalse(await self._eval(None, IsNullOperator(False)))

    async def test_and_operator_all_true(self):
        op = AndOperator((
            ComparisonOperator('$gt', 5),
            ComparisonOperator('$lt', 10),
        ))
        self.assertTrue(await self._eval(7, op))

    async def test_and_operator_one_false(self):
        op = AndOperator((
            ComparisonOperator('$gt', 5),
            ComparisonOperator('$lt', 10),
        ))
        self.assertFalse(await self._eval(12, op))

    async def test_or_operator_one_true(self):
        op = OrOperator((
            EqOperator('active'),
            EqOperator('pending'),
        ))
        self.assertTrue(await self._eval('pending', op))

    async def test_or_operator_none_true(self):
        op = OrOperator((
            EqOperator('active'),
            EqOperator('pending'),
        ))
        self.assertFalse(await self._eval('deleted', op))

    async def test_composite_matches(self):
        query = CompositeQuery({
            'status': EqOperator('active'),
            'name': EqOperator('Alice'),
        })
        state = {'status': 'active', 'name': 'Alice', 'extra': 'ignored'}
        self.assertTrue(await self._eval(state, query))

    async def test_composite_not_matches(self):
        query = CompositeQuery({
            'status': EqOperator('active'),
            'name': EqOperator('Alice'),
        })
        state = {'status': 'inactive', 'name': 'Alice'}
        self.assertFalse(await self._eval(state, query))

    async def test_composite_non_dict_state(self):
        query = CompositeQuery({'status': EqOperator('active')})
        self.assertFalse(await self._eval(42, query))

    async def test_nested_composite_without_resolver(self):
        query = CompositeQuery({
            'address': CompositeQuery({
                'city': EqOperator('Moscow'),
            }),
        })
        state = {'address': {'city': 'Moscow', 'street': 'Main'}}
        self.assertTrue(await self._eval(state, query))

        state_wrong = {'address': {'city': 'London'}}
        self.assertFalse(await self._eval(state_wrong, query))

    async def test_composite_with_comparison(self):
        query = CompositeQuery({
            'name': EqOperator('John'),
            'age': AndOperator((
                ComparisonOperator('$gte', 18),
                ComparisonOperator('$lt', 65),
            )),
        })
        state = {'name': 'John', 'age': 30}
        self.assertTrue(await self._eval(state, query))

        state_young = {'name': 'John', 'age': 15}
        self.assertFalse(await self._eval(state_young, query))

    async def test_composite_with_or(self):
        query = CompositeQuery({
            'status': OrOperator((
                EqOperator('active'),
                EqOperator('pending'),
            )),
        })
        self.assertTrue(await self._eval({'status': 'active'}, query))
        self.assertTrue(await self._eval({'status': 'pending'}, query))
        self.assertFalse(await self._eval({'status': 'deleted'}, query))

    async def test_composite_with_in(self):
        query = CompositeQuery({
            'status': InOperator(('active', 'pending')),
        })
        self.assertTrue(await self._eval({'status': 'active'}, query))
        self.assertFalse(await self._eval({'status': 'deleted'}, query))

    async def test_parsed_simple_pattern(self):
        query = QueryParser().parse({'status': 'active'})
        self.assertTrue(
            await self._eval({'status': 'active', 'name': 'test'}, query)
        )
        self.assertFalse(
            await self._eval({'status': 'inactive', 'name': 'test'}, query)
        )

    async def test_rel_without_resolver_delegates_to_inner(self):
        query = RelOperator(CompositeQuery({
            'name': EqOperator('Active'),
        }))
        self.assertTrue(await self._eval({'name': 'Active'}, query))
        self.assertFalse(await self._eval({'name': 'Inactive'}, query))


# =============================================================================
# Tests for EvaluateVisitor - Nested Lookup (2 levels)
# =============================================================================

class EvaluateVisitorNestedLookupTestCase(IsolatedAsyncioTestCase):
    """Tests for EvaluateVisitor nested lookup with object resolver."""

    def setUp(self):
        self.session = MockSession()

        self.status_storage = {
            'active': {'id': 'active', 'name': 'Active'},
            'inactive': {'id': 'inactive', 'name': 'Inactive'},
        }

        status_resolver = StubObjectResolver({})
        self.resolver = StubObjectResolver({
            'status_id': (self.status_storage, status_resolver),
        })

    def _eval(self, state, query):
        return query.accept(EvaluateVisitor(state, self.session, self.resolver))

    async def test_nested_lookup_matches(self):
        query = CompositeQuery({
            'status_id': RelOperator(CompositeQuery({
                'name': EqOperator('Active'),
            })),
        })
        state = {'id': 1, 'status_id': 'active', 'name': 'Alice'}
        self.assertTrue(await self._eval(state, query))

    async def test_nested_lookup_not_matches(self):
        query = CompositeQuery({
            'status_id': RelOperator(CompositeQuery({
                'name': EqOperator('Active'),
            })),
        })
        state = {'id': 2, 'status_id': 'inactive', 'name': 'Bob'}
        self.assertFalse(await self._eval(state, query))

    async def test_nested_lookup_fk_is_none(self):
        query = CompositeQuery({
            'status_id': RelOperator(CompositeQuery({
                'name': EqOperator('Active'),
            })),
        })
        state = {'id': 3, 'status_id': None, 'name': 'Charlie'}
        self.assertFalse(await self._eval(state, query))

    async def test_nested_lookup_foreign_not_found(self):
        query = CompositeQuery({
            'status_id': RelOperator(CompositeQuery({
                'name': EqOperator('Active'),
            })),
        })
        state = {'id': 4, 'status_id': 'unknown', 'name': 'Dave'}
        self.assertFalse(await self._eval(state, query))

    async def test_simple_value_with_nested_lookup(self):
        query = CompositeQuery({
            'name': EqOperator('Alice'),
            'status_id': RelOperator(CompositeQuery({
                'name': EqOperator('Active'),
            })),
        })
        state_alice = {'id': 1, 'status_id': 'active', 'name': 'Alice'}
        self.assertTrue(await self._eval(state_alice, query))

        state_bob = {'id': 2, 'status_id': 'inactive', 'name': 'Bob'}
        self.assertFalse(await self._eval(state_bob, query))

    async def test_nested_lookup_with_comparison(self):
        self.status_storage['high'] = {'id': 'high', 'name': 'High', 'priority': 10}
        self.status_storage['low'] = {'id': 'low', 'name': 'Low', 'priority': 1}

        query = CompositeQuery({
            'status_id': RelOperator(CompositeQuery({
                'priority': ComparisonOperator('$gte', 5),
            })),
        })

        state_high = {'id': 1, 'status_id': 'high', 'name': 'Alice'}
        self.assertTrue(await self._eval(state_high, query))

        state_low = {'id': 2, 'status_id': 'low', 'name': 'Bob'}
        self.assertFalse(await self._eval(state_low, query))

    async def test_non_relation_field_with_resolver(self):
        query = CompositeQuery({
            'name': EqOperator('Alice'),
        })
        state = {'id': 1, 'status_id': 'active', 'name': 'Alice'}
        self.assertTrue(await self._eval(state, query))


# =============================================================================
# Tests for EvaluateVisitor - Three Table Cascade
# =============================================================================

class EvaluateVisitorThreeTableCascadeTestCase(IsolatedAsyncioTestCase):
    """Three-table cascade for EvaluateVisitor: Employee -> Company -> Country."""

    def setUp(self):
        self.session = MockSession()

        self.country_storage = {
            'US': {'id': 'US', 'code': 'US', 'continent': 'America'},
            'UK': {'id': 'UK', 'code': 'UK', 'continent': 'Europe'},
            'JP': {'id': 'JP', 'code': 'JP', 'continent': 'Asia'},
        }

        self.company_storage = {
            1: {
                'id': 1, 'country_id': 'US', 'name': 'Acme',
                'type': 'tech', 'revenue': 2000000,
            },
            2: {
                'id': 2, 'country_id': 'UK', 'name': 'BritCo',
                'type': 'finance', 'revenue': 500000,
            },
            3: {
                'id': 3, 'country_id': 'JP', 'name': 'TokyoTech',
                'type': 'tech', 'revenue': 800000,
            },
        }

        country_resolver = StubObjectResolver({})
        company_resolver = StubObjectResolver({
            'country_id': (self.country_storage, country_resolver),
        })
        self.resolver = StubObjectResolver({
            'company_id': (self.company_storage, company_resolver),
        })

    def _eval(self, state, query):
        return query.accept(EvaluateVisitor(state, self.session, self.resolver))

    async def test_three_table_cascade_matches(self):
        query = CompositeQuery({
            'name': EqOperator('John'),
            'status': EqOperator('active'),
            'company_id': RelOperator(CompositeQuery({
                'type': EqOperator('tech'),
                'country_id': RelOperator(CompositeQuery({
                    'code': EqOperator('US'),
                })),
            })),
        })

        employee = {
            'id': 1, 'company_id': 1, 'name': 'John',
            'age': 30, 'status': 'active',
        }
        self.assertTrue(await self._eval(employee, query))

    async def test_three_table_cascade_not_matches_middle(self):
        query = CompositeQuery({
            'company_id': RelOperator(CompositeQuery({
                'type': EqOperator('tech'),
            })),
        })

        employee = {'id': 2, 'company_id': 2, 'name': 'Jane', 'age': 25, 'status': 'active'}
        self.assertFalse(await self._eval(employee, query))

    async def test_three_table_cascade_not_matches_deepest(self):
        query = CompositeQuery({
            'company_id': RelOperator(CompositeQuery({
                'country_id': RelOperator(CompositeQuery({
                    'code': EqOperator('UK'),
                })),
            })),
        })

        # Employee at Acme (US) — should fail
        employee = {'id': 1, 'company_id': 1, 'name': 'John', 'age': 30, 'status': 'active'}
        self.assertFalse(await self._eval(employee, query))

        # Employee at BritCo (UK) — should match
        employee_uk = {'id': 2, 'company_id': 2, 'name': 'Jane', 'age': 25, 'status': 'active'}
        self.assertTrue(await self._eval(employee_uk, query))

    async def test_or_in_cascade(self):
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

        employee_us = {'id': 1, 'company_id': 1, 'name': 'John', 'age': 30, 'status': 'active'}
        self.assertTrue(await self._eval(employee_us, query))

        employee_uk = {'id': 2, 'company_id': 2, 'name': 'Jane', 'age': 25, 'status': 'active'}
        self.assertTrue(await self._eval(employee_uk, query))

        employee_jp = {'id': 3, 'company_id': 3, 'name': 'Yuki', 'age': 28, 'status': 'active'}
        self.assertFalse(await self._eval(employee_jp, query))

    async def test_cascade_with_all_operators(self):
        query = CompositeQuery({
            'name': EqOperator('John'),
            'age': ComparisonOperator('$gt', 25),
            'company_id': RelOperator(CompositeQuery({
                'type': EqOperator('tech'),
                'revenue': ComparisonOperator('$gte', 1000000),
                'country_id': RelOperator(CompositeQuery({
                    'code': EqOperator('US'),
                })),
            })),
        })

        employee = {'id': 1, 'company_id': 1, 'name': 'John', 'age': 30, 'status': 'active'}
        self.assertTrue(await self._eval(employee, query))

        employee2 = {'id': 4, 'company_id': 3, 'name': 'John', 'age': 30, 'status': 'active'}
        self.assertFalse(await self._eval(employee2, query))

    async def test_cascade_company_not_found(self):
        query = CompositeQuery({
            'company_id': RelOperator(CompositeQuery({
                'type': EqOperator('tech'),
            })),
        })

        employee = {'id': 5, 'company_id': 999, 'name': 'Ghost', 'age': 0, 'status': 'unknown'}
        self.assertFalse(await self._eval(employee, query))


# =============================================================================
# Tests for EvaluateWalker.evaluate_sync() - Basic (no resolver)
# =============================================================================

class EvaluateWalkerSyncBasicTestCase(IsolatedAsyncioTestCase):
    """Basic tests for evaluate_sync() without object resolver."""

    def setUp(self):
        self.walker = EvaluateWalker()

    def test_eq_matches(self):
        """EqOperator should match equal value."""
        self.assertTrue(self.walker.evaluate_sync(EqOperator(42), 42))

    def test_eq_not_matches(self):
        """EqOperator should not match different value."""
        self.assertFalse(self.walker.evaluate_sync(EqOperator(42), 99))

    def test_eq_none(self):
        """EqOperator(None) should match None."""
        self.assertTrue(self.walker.evaluate_sync(EqOperator(None), None))

    def test_eq_string(self):
        """EqOperator should match string value."""
        self.assertTrue(self.walker.evaluate_sync(EqOperator('active'), 'active'))

    def test_comparison_ne(self):
        """$ne should match when values differ."""
        op = ComparisonOperator('$ne', 'deleted')
        self.assertTrue(self.walker.evaluate_sync(op, 'active'))
        self.assertFalse(self.walker.evaluate_sync(op, 'deleted'))

    def test_comparison_gt(self):
        """$gt should match when actual > expected."""
        op = ComparisonOperator('$gt', 10)
        self.assertTrue(self.walker.evaluate_sync(op, 15))
        self.assertFalse(self.walker.evaluate_sync(op, 10))
        self.assertFalse(self.walker.evaluate_sync(op, 5))

    def test_comparison_gte(self):
        """$gte should match when actual >= expected."""
        op = ComparisonOperator('$gte', 10)
        self.assertTrue(self.walker.evaluate_sync(op, 15))
        self.assertTrue(self.walker.evaluate_sync(op, 10))
        self.assertFalse(self.walker.evaluate_sync(op, 5))

    def test_comparison_lt(self):
        """$lt should match when actual < expected."""
        op = ComparisonOperator('$lt', 10)
        self.assertTrue(self.walker.evaluate_sync(op, 5))
        self.assertFalse(self.walker.evaluate_sync(op, 10))
        self.assertFalse(self.walker.evaluate_sync(op, 15))

    def test_comparison_lte(self):
        """$lte should match when actual <= expected."""
        op = ComparisonOperator('$lte', 10)
        self.assertTrue(self.walker.evaluate_sync(op, 5))
        self.assertTrue(self.walker.evaluate_sync(op, 10))
        self.assertFalse(self.walker.evaluate_sync(op, 15))

    def test_in_operator_matches(self):
        """$in should match when value is in the list."""
        op = InOperator(('active', 'pending'))
        self.assertTrue(self.walker.evaluate_sync(op, 'active'))
        self.assertTrue(self.walker.evaluate_sync(op, 'pending'))

    def test_in_operator_not_matches(self):
        """$in should not match when value is not in the list."""
        op = InOperator(('active', 'pending'))
        self.assertFalse(self.walker.evaluate_sync(op, 'deleted'))

    def test_is_null_true_matches_none(self):
        """IsNullOperator(True) should match None."""
        self.assertTrue(self.walker.evaluate_sync(IsNullOperator(True), None))

    def test_is_null_true_not_matches_value(self):
        """IsNullOperator(True) should not match non-None."""
        self.assertFalse(self.walker.evaluate_sync(IsNullOperator(True), 42))

    def test_is_null_false_matches_value(self):
        """IsNullOperator(False) should match non-None."""
        self.assertTrue(self.walker.evaluate_sync(IsNullOperator(False), 42))

    def test_is_null_false_not_matches_none(self):
        """IsNullOperator(False) should not match None."""
        self.assertFalse(self.walker.evaluate_sync(IsNullOperator(False), None))

    def test_and_operator_all_true(self):
        """AndOperator should match when all operands match."""
        op = AndOperator((
            ComparisonOperator('$gt', 5),
            ComparisonOperator('$lt', 10),
        ))
        self.assertTrue(self.walker.evaluate_sync(op, 7))

    def test_and_operator_one_false(self):
        """AndOperator should not match when any operand fails."""
        op = AndOperator((
            ComparisonOperator('$gt', 5),
            ComparisonOperator('$lt', 10),
        ))
        self.assertFalse(self.walker.evaluate_sync(op, 12))

    def test_or_operator_one_true(self):
        """OrOperator should match when any operand matches."""
        op = OrOperator((
            EqOperator('active'),
            EqOperator('pending'),
        ))
        self.assertTrue(self.walker.evaluate_sync(op, 'pending'))

    def test_or_operator_none_true(self):
        """OrOperator should not match when no operand matches."""
        op = OrOperator((
            EqOperator('active'),
            EqOperator('pending'),
        ))
        self.assertFalse(self.walker.evaluate_sync(op, 'deleted'))

    def test_composite_matches(self):
        """CompositeQuery should match when all fields match."""
        query = CompositeQuery({
            'status': EqOperator('active'),
            'name': EqOperator('Alice'),
        })
        state = {'status': 'active', 'name': 'Alice', 'extra': 'ignored'}
        self.assertTrue(self.walker.evaluate_sync(query, state))

    def test_composite_not_matches(self):
        """CompositeQuery should not match when any field fails."""
        query = CompositeQuery({
            'status': EqOperator('active'),
            'name': EqOperator('Alice'),
        })
        state = {'status': 'inactive', 'name': 'Alice'}
        self.assertFalse(self.walker.evaluate_sync(query, state))

    def test_composite_non_dict_state(self):
        """CompositeQuery should return False for non-dict state."""
        query = CompositeQuery({'status': EqOperator('active')})
        self.assertFalse(self.walker.evaluate_sync(query, 42))

    def test_nested_composite(self):
        """Nested CompositeQuery should match nested dict state."""
        query = CompositeQuery({
            'address': CompositeQuery({
                'city': EqOperator('Moscow'),
            }),
        })
        state = {'address': {'city': 'Moscow', 'street': 'Main'}}
        self.assertTrue(self.walker.evaluate_sync(query, state))

        state_wrong = {'address': {'city': 'London'}}
        self.assertFalse(self.walker.evaluate_sync(query, state_wrong))

    def test_composite_with_comparison(self):
        """CompositeQuery with comparison operators."""
        query = CompositeQuery({
            'name': EqOperator('John'),
            'age': AndOperator((
                ComparisonOperator('$gte', 18),
                ComparisonOperator('$lt', 65),
            )),
        })
        state = {'name': 'John', 'age': 30}
        self.assertTrue(self.walker.evaluate_sync(query, state))

        state_young = {'name': 'John', 'age': 15}
        self.assertFalse(self.walker.evaluate_sync(query, state_young))

    def test_composite_with_or(self):
        """CompositeQuery with $or operator."""
        query = CompositeQuery({
            'status': OrOperator((
                EqOperator('active'),
                EqOperator('pending'),
            )),
        })
        self.assertTrue(self.walker.evaluate_sync(query, {'status': 'active'}))
        self.assertTrue(self.walker.evaluate_sync(query, {'status': 'pending'}))
        self.assertFalse(self.walker.evaluate_sync(query, {'status': 'deleted'}))

    def test_composite_with_in(self):
        """CompositeQuery with $in operator."""
        query = CompositeQuery({
            'status': InOperator(('active', 'pending')),
        })
        self.assertTrue(self.walker.evaluate_sync(query, {'status': 'active'}))
        self.assertFalse(self.walker.evaluate_sync(query, {'status': 'deleted'}))

    def test_parsed_simple_pattern(self):
        """Parsed query should work with evaluate_sync."""
        query = QueryParser().parse({'status': 'active'})
        self.assertTrue(
            self.walker.evaluate_sync(query, {'status': 'active', 'name': 'test'})
        )
        self.assertFalse(
            self.walker.evaluate_sync(query, {'status': 'inactive', 'name': 'test'})
        )

    def test_rel_without_resolver_delegates_to_inner(self):
        """RelOperator without resolver delegates to inner query."""
        query = RelOperator(CompositeQuery({
            'name': EqOperator('Active'),
        }))
        state = {'name': 'Active'}
        self.assertTrue(self.walker.evaluate_sync(query, state))

        state_wrong = {'name': 'Inactive'}
        self.assertFalse(self.walker.evaluate_sync(query, state_wrong))

    def test_partial_criteria_matches_full_state(self):
        """Partial criteria should match state with extra fields (diamond scenario)."""
        query = CompositeQuery({
            'id': EqOperator('uuid-123'),
        })
        state = {'id': 'uuid-123', 'attr2': 'some_value'}
        self.assertTrue(self.walker.evaluate_sync(query, state))

    def test_partial_criteria_not_matches(self):
        """Partial criteria should not match when checked field differs."""
        query = CompositeQuery({
            'id': EqOperator('uuid-123'),
        })
        state = {'id': 'uuid-456', 'attr2': 'some_value'}
        self.assertFalse(self.walker.evaluate_sync(query, state))

    def test_nested_composite_partial_criteria(self):
        """Partial nested criteria should match (composite PK diamond scenario)."""
        query = CompositeQuery({
            'id': CompositeQuery({
                'first_model_id': EqOperator('uuid-A'),
            }),
        })
        state = {'id': {'id': 'local-pk', 'first_model_id': 'uuid-A'}, 'attr2': 'foo'}
        self.assertTrue(self.walker.evaluate_sync(query, state))

        state_wrong = {'id': {'id': 'local-pk', 'first_model_id': 'uuid-B'}, 'attr2': 'foo'}
        self.assertFalse(self.walker.evaluate_sync(query, state_wrong))


if __name__ == '__main__':
    unittest.main()
