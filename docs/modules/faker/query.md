# Query DSL

```{index} Query DSL, MongoDB-like Query, Operators, Visitor Pattern, Query Compiler
```


## Overview

The query module (`ascetic_ddd.faker.domain.query`) provides a MongoDB-like
query DSL for specifying criteria in the faker provider hierarchy. It is the
unified language through which providers communicate constraints:
`require({'$gt': start_date})` instead of `require(concrete_value)`.

See {doc}`/adr/0006-mongodb-like-query-dsl-for-faker-providers` for the
architectural rationale.


## Why MongoDB-like Syntax?

MongoDB query syntax naturally separates the **operator with its right operand**
from the **left operand** (the field name):

```python
{'$gt': 5}           # operator + right operand, no field name
{'$eq': 27}          # same pattern
{'age': {'$gt': 5}}  # field name + operator + right operand
```

This is ideal for the provider hierarchy. When a parent provider calls
`child.require({'$gt': start_date})`, the child receives only the operator and
the value. The field name is determined by the child's position in the provider
tree, not by the caller. Providers stay decoupled.

In contrast, SQL-like syntax (`age > 5`) binds all three parts together,
requiring the caller to know the field name.


## Query Syntax

### Equality

Exact value match. Scalar values are implicit `$eq`:

```python
require(27)              # -> EqOperator(27)
require({'$eq': 27})     # -> EqOperator(27), same result
require({'$eq': None})   # -> EqOperator(None)
```


### Comparison

```python
{'$ne': 'deleted'}    # not equal
{'$gt': 5}            # greater than
{'$gte': 5}           # greater than or equal
{'$lt': 10}           # less than
{'$lte': 10}          # less than or equal
```


### Range (Implicit AND)

Multiple operators at the same level are combined with implicit AND:

```python
{'$gt': 5, '$lt': 10}   # 5 < value < 10
```


### Membership

```python
{'$in': ['active', 'pending']}   # value in list
```


### Null Check

```python
{'$is_null': True}    # value is None
{'$is_null': False}   # value is not None
```


### Logical NOT

Negates the result of the inner expression:

```python
{'$not': {'$eq': 'deleted'}}        # NOT equal to 'deleted'
{'$not': {'$gt': 65}}               # NOT greater than 65
{'status': {'$not': {'$eq': 'deleted'}}}  # in composite
```


### Logical OR

```python
{'$or': [{'$eq': 'active'}, {'$eq': 'pending'}]}
```


### Array Quantifiers (`$any`, `$all`)

`$any` — existential quantifier: at least one array element matches:

```python
{'items': {'$any': {'status': {'$eq': 'shipped'}}}}
```

`$all` — universal quantifier: every array element matches:

```python
{'items': {'$all': {'status': {'$eq': 'active'}}}}
```


### Array Length (`$len`)

Applies a predicate to the array length:

```python
{'items': {'$len': {'$gt': 2}}}      # more than 2 items
{'items': {'$len': {'$eq': 0}}}      # empty array
{'items': {'$len': {'$gte': 1}}}     # at least 1 item
```

Can be combined with `$any` at the same level via implicit AND:

```python
{'items': {'$any': {'price': {'$gt': 100}}, '$len': {'$gte': 1}}}
```


### Composite (Multi-field)

Multiple field constraints. Used for composite primary keys or multi-field criteria:

```python
{'tenant_id': {'$eq': 15}, 'local_id': {'$eq': 27}}
{'tenant_id': 15, 'local_id': 27}  # same, implicit $eq
```


### Related Aggregate (`$rel`)

Constraints on a **related** aggregate (used by `ReferenceProvider`):

```python
# Select by aggregate attribute
{'$rel': {'is_active': {'$eq': True}}}

# Combined: PK + attribute
{'$rel': {'is_active': {'$eq': True}, 'id': {'$eq': 27}}}

# Nested: three-level cascade
{'company_id': {'$rel': {
    'type': {'$eq': 'tech'},
    'country_id': {'$rel': {'code': {'$eq': 'US'}}}
}}}
```


### Combined Examples

```python
# Business invariant: course session date after course start
session_provider.start_date.require({'$gte': course_start_date})

# Active company in IT department
ref_provider.require({'$rel': {
    'is_active': {'$eq': True},
    'department': {'$eq': 'IT'}
}})

# Nullable FK with null check
{'deleted_at': {'$is_null': True}, 'status': {'$eq': 'active'}}

# Range with exclusion
{'age': {'$gt': 18, '$lt': 65}, 'status': {'$ne': 'blocked'}}
```


## Architecture

The module follows a three-layer architecture:

```
                   ┌─────────────┐
                   │   Parser    │  dict/scalar → operator tree
                   └──────┬──────┘
                          │
                   ┌──────▼──────┐
                   │  Operators  │  AST nodes (IQueryOperator)
                   └──────┬──────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
   ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
   │  Visitors   │ │  Evaluator  │ │ PgCompiler  │
   │ (to dict /  │ │ (in-memory  │ │ (SQL + @>)  │
   │ plain value)│ │  matching)  │ │             │
   └─────────────┘ └─────────────┘ └─────────────┘
```

All operations over the operator tree use the **Visitor pattern**
(`IQueryVisitor`), keeping operator classes stable when new operations are added.


## Operator Tree

The parser converts queries into an AST of `IQueryOperator` nodes:

| Operator | Syntax | AST Node |
|----------|--------|----------|
| `$eq` | `{'$eq': 27}` or `27` | `EqOperator(value)` |
| `$ne` | `{'$ne': 'deleted'}` | `ComparisonOperator('$ne', value)` |
| `$gt`, `$gte`, `$lt`, `$lte` | `{'$gt': 5}` | `ComparisonOperator(op, value)` |
| `$in` | `{'$in': [1, 2]}` | `InOperator(values)` |
| `$is_null` | `{'$is_null': True}` | `IsNullOperator(value)` |
| `$not` | `{'$not': {...}}` | `NotOperator(operand)` |
| `$any` | `{'$any': {...}}` | `AnyElementOperator(query)` |
| `$all` | `{'$all': {...}}` | `AllElementsOperator(query)` |
| `$len` | `{'$len': {...}}` | `LenOperator(query)` |
| `$or` | `{'$or': [...]}` | `OrOperator(operands)` |
| implicit AND | `{'$gt': 5, '$lt': 10}` | `AndOperator(operands)` |
| `$rel` | `{'$rel': {...}}` | `RelOperator(query)` |
| fields | `{'a': ..., 'b': ...}` | `CompositeQuery(fields)` |

All operators are:

- **Hashable** and **equality-comparable** (usable in sets and dicts)
- **Mergeable** via `__add__` (for diamond topologies)
- **Visitable** via `accept(visitor)`


## Parsing

```python
from ascetic_ddd.faker.domain.query import parse_query

# Two-stage: parse dict → operator tree, then normalize (unwrap redundant $eq)
op = parse_query({'status': {'$eq': 'active'}, 'age': {'$gt': 18}})
# -> CompositeQuery({
#     'status': EqOperator('active'),
#     'age': ComparisonOperator('$gt', 18)
# })
```

The parser validates input and raises `ValueError` for:

- Empty query dicts
- Unknown operators
- Mixed operators and fields at the same level
- Invalid operand types (e.g., non-bool for `$is_null`, non-list for `$in`)


## Operator Merging

All operators support `__add__` for merging criteria from multiple sources.
This is essential for diamond topologies where multiple paths through the
provider graph contribute criteria to the same provider:

```python
from ascetic_ddd.faker.domain.query.operators import (
    RelOperator, CompositeQuery, EqOperator, MergeConflict
)

# Path 1: active company
rel1 = RelOperator(CompositeQuery({'is_active': EqOperator(True)}))

# Path 2: specific ID
rel2 = RelOperator(CompositeQuery({'id': EqOperator(27)}))

# Merge: both constraints combined
merged = rel1 + rel2
# -> RelOperator(CompositeQuery({
#     'is_active': EqOperator(True),
#     'id': EqOperator(27)
# }))
```

Merge rules:

- **Same type, same value** → returns self
- **Same type, different value** → raises `MergeConflict`
- **Different types** → returns `NotImplemented` (triggers `TypeError`)
- **CompositeQuery** → field-by-field recursive merge
- **RelOperator** → delegates to inner `CompositeQuery.__add__`


## Visitors

### QueryToDictVisitor

Serializes operator tree back to dict format with operator keys:

```python
from ascetic_ddd.faker.domain.query import query_to_dict

query_to_dict(EqOperator(5))
# -> {'$eq': 5}

query_to_dict(CompositeQuery({'status': EqOperator('active')}))
# -> {'status': {'$eq': 'active'}}
```


### QueryToPlainValueVisitor

Extracts plain values without operator keys (for specifications):

```python
from ascetic_ddd.faker.domain.query import query_to_plain_value

query_to_plain_value(EqOperator(5))
# -> 5

query_to_plain_value(CompositeQuery({'a': EqOperator(1), 'b': EqOperator(2)}))
# -> {'a': 1, 'b': 2}
```

For non-equality operators, the operator key is preserved:

```python
query_to_plain_value(ComparisonOperator('$gt', 5))
# -> {'$gt': 5}

query_to_plain_value(IsNullOperator(True))
# -> {'$is_null': True}
```


## Evaluation

Two implementations for checking if an object state matches query criteria:


### EvaluateWalker (procedural)

```python
from ascetic_ddd.faker.domain.query import EvaluateWalker

walker = EvaluateWalker()
state = {'status': 'active', 'age': 25}
query = parse_query({'status': {'$eq': 'active'}, 'age': {'$gt': 18}})

# Async evaluation (supports $rel with IObjectResolver)
result = await walker.evaluate(session, query, state)  # True

# Sync evaluation (no $rel resolver support)
result = walker.evaluate_sync(query, state)  # True
```


### EvaluateVisitor (visitor pattern)

```python
from ascetic_ddd.faker.domain.query import EvaluateVisitor

evaluator = EvaluateVisitor(state, session, object_resolver)
result = await query.accept(evaluator)
```


### IObjectResolver

Interface for resolving `$rel` fields to foreign object state during
evaluation. Decouples the evaluator from providers/repositories:

```python
from ascetic_ddd.faker.domain.query import IObjectResolver

class MyResolver(IObjectResolver):
    async def resolve(self, session, field, fk_value):
        # Returns (foreign_state_dict, nested_resolver) or (None, None)
        ...
```


## PostgreSQL Compilation

The `PgQueryCompiler` compiles the operator tree to SQL optimized for
PostgreSQL JSONB with GIN indexes:

```python
from ascetic_ddd.faker.infrastructure.query.pg_query_compiler import PgQueryCompiler

compiler = PgQueryCompiler(target_value_expr="value")
sql, params = compiler.compile(
    parse_query({'status': 'active', 'age': {'$gt': 18}})
)
# sql:    "value @> %s AND value->'age' > %s"
# params: (Jsonb({'status': 'active'}), 18)
```

Compilation rules:

| Operator | SQL |
|----------|-----|
| `$eq` (in composite) | Collapsed into single `value @> %s` (GIN index) |
| `$ne` | `NOT (value @> %s)` |
| `$gt`, `$gte`, `$lt`, `$lte` | `value->'field' > %s` |
| `$in` | `(value @> %s OR value @> %s OR ...)` |
| `$is_null` | `value->'field' IS NULL` / `IS NOT NULL` |
| `$not` | `NOT (inner_sql)` |
| `$any` | `EXISTS (SELECT 1 FROM jsonb_array_elements(...) AS rt WHERE inner_sql)` |
| `$all` | `NOT EXISTS (SELECT 1 FROM jsonb_array_elements(...) AS rt WHERE NOT (inner_sql))` |
| `$len` | `jsonb_array_length(json_path) op %s` (standard SQL comparison) |
| `$or` | `(sub1 OR sub2 OR ...)` |
| `$rel` (with resolver) | `EXISTS (SELECT 1 FROM related_table rt1 WHERE ...)` |

Multiple `$eq` values within a `CompositeQuery` are collapsed into a single
`@>` containment check for optimal GIN index usage.


### IRelationResolver

Interface for resolving field names to SQL table metadata (used by
`PgQueryCompiler` for `$rel` → `EXISTS` subqueries):

```python

from ascetic_ddd.faker.infrastructure.query.pg_query_compiler import RelationInfo, IRelationResolver


class MyResolver(IRelationResolver):
    def resolve(self, field):
        # Returns RelationInfo(table, pk_field, nested_resolver) or None
        ...
```


## Extending with New Operators

Adding a new operator requires:

1. **Operator class** in `operators.py` — implement `IQueryOperator` (`accept`,
   `__eq__`, `__hash__`, `__add__`)
2. **Visitor method** — add `visit_xxx` to `IQueryVisitor` interface
3. **Parser case** — add `elif op_name == '$xxx':` in `_parse_single_operator()`
4. **Visitor implementations** — add `visit_xxx` to all visitors:
   `QueryToDictVisitor`, `QueryToPlainValueVisitor`, `EvaluateWalker`,
   `EvaluateVisitor`, `PgQueryCompiler`

Existing operators and visitors are not modified — this is the Open/Closed
Principle enabled by the Visitor pattern.


## Go Portability

The module is designed for portability to Go
(see {doc}`/adr/0003-go-portability`):

- No metaclass magic or decorators
- `IQueryVisitor` maps to a Go interface with method per operator
- `accept()` dispatch maps to a Go `switch` on concrete type
- `isinstance` checks in `EvaluateWalker` map to Go type assertions
- C-style string formatting (`%s`, `%d`) throughout


## API Reference

See the {doc}`/api/index` section for auto-generated API documentation of:

- {mod}`ascetic_ddd.faker.domain.query.operators`
- {mod}`ascetic_ddd.faker.domain.query.parser`
- {mod}`ascetic_ddd.faker.domain.query.visitors`
- {mod}`ascetic_ddd.faker.domain.query.evaluate_visitor`
- {mod}`ascetic_ddd.faker.infrastructure.query.pg_query_compiler`
