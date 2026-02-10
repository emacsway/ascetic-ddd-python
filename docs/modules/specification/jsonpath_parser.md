```{index} Native JSONPath Parser, JSONPath, Specification Pattern
```

# Native JSONPath Parser (No External Dependencies)

## Description

A fully self-contained JSONPath expression parser that **requires no external libraries**. Directly converts RFC 9535 compatible JSONPath expressions into Specification AST.

## Key Advantages

- **No external dependencies** - runs on pure Python
- **RFC 9535 compatibility** - support for standard operators (`==`, `&&`, `||`, `!`)
- **Parentheses** - logical expression grouping (`$[?(@.age >= 18 && @.age <= 65) && @.active == true]`)
- **Full control** - transparent parsing logic
- **Lightweight** - minimal code, only the essentials
- **Easy to maintain** - all code in a single file
- **Full functionality** - all logical operators including NOT
- **Nested wildcards** - filtering by nested collections
- **Nested paths** - access to nested fields (`$.a.b.c[?@.x > 1]`)

## Usage

```python
from ascetic_ddd.specification.domain.jsonpath.jsonpath_parser import parse

# Create specification
spec = parse("$[?(@.age > %d)]")


# Create context
class DictContext:
    def __init__(self, data):
        self._data = data

    def get(self, key):
        return self._data[key]


user = DictContext({"age": 30})

# Check match
result = spec.match(user, (25,))  # True
```

## Architecture

### Components

1. **Lexer** - Tokenization of JSONPath expressions
   - Recognizes operators, identifiers, literals
   - Handles placeholders

2. **Parser** - Token to AST conversion
   - Recursive expression parser
   - Direct creation of Specification nodes

3. **Placeholder Binding** - Parameter binding
   - Support for positional and named parameters
   - Typed placeholders (%s, %d, %f)

### Parsing Process

```
JSONPath Template
      ↓
[Lexer] Tokenization
      ↓
Token Stream
      ↓
[Parser] Expression Parsing
      ↓
Specification AST
      ↓
[Binding] Placeholder Values
      ↓
Bound AST
      ↓
[Evaluation] EvaluateVisitor
      ↓
Boolean Result
```

## RFC 9535 Compliance

Full support for the RFC 9535 standard:

### Comparison Operators
- `==` - Equal (RFC 9535: double sign)
- `!=` - Not equal
- `>` - Greater than
- `<` - Less than
- `>=` - Greater than or equal
- `<=` - Less than or equal

### Logical Operators
- `&&` - Logical AND (RFC 9535)
- `||` - Logical OR (RFC 9535)
- `!` - Logical NOT (RFC 9535)

### Parameterization
```python
# Positional
parse("$[?@.age > %d]")            # Integer
parse("$[?@.name == %s]")          # String (RFC 9535: ==)
parse("$[?@.price > %f]")          # Floating point number

# Named
parse("$[?@.age > %(min_age)d]")
parse("$[?@.name == %(name)s]")    # RFC 9535: ==

# Logical operators (RFC 9535)
parse("$[?@.age > %d && @.active == %s]")   # AND
parse("$[?@.age < %d || @.age > %d]")       # OR
parse("$[?!(@.active == %s)]")              # NOT
```

### Collections with Wildcard
```python
spec = parse("$.items[*][?(@.price > %f)]")

from ascetic_ddd.specification.domain.evaluate_visitor import CollectionContext

item1 = DictContext({"name": "Laptop", "price": 999.99})
item2 = DictContext({"name": "Mouse", "price": 29.99})

collection = CollectionContext([item1, item2])
store = DictContext({"items": collection})

# Check if there is at least one item with price > 500
spec.match(store, (500.0,))  # True
```

### Nested Wildcards
```python
# Nested collections: categories -> items
spec = parse("$.categories[*][?@.items[*][?@.price > %f]]")

# Create data structure
item1 = DictContext({"name": "Laptop", "price": 999.0})
items = CollectionContext([item1])
category = DictContext({"name": "Electronics", "items": items})

categories = CollectionContext([category])
store = DictContext({"categories": categories})

# Is there a category with an item costing more than 500?
spec.match(store, (500.0,))  # True
```

## Supported Features

The current implementation supports:
- Simple filters: `$[?@.field op value]`
- Logical expressions: `$[?@.a > 1 && @.b == 2]`, `$[?@.a < 1 || @.a > 10]`
- Negation: `$[?!(@.active == true)]`
- Wildcard collections: `$.collection[*][?@.field op value]`
- Nested wildcards: `$.categories[*][?@.items[*][?@.price > 100]]`
- Nested paths: `$.a.b.c[?@.x > 1]`, `$[?@.a.b.c > 1]`

Not supported (yet):
- JSONPath functions (len, min, max, etc.)
- Array indices: `$.items[0]`, `$.items[1:5]`

## Testing

```bash
# Run native parser tests
python -m unittest ascetic_ddd.specification.domain.jsonpath.test_jsonpath_parser -v

# All tests
python -m unittest discover -s ascetic_ddd/specification -p "test_*.py" -v
```

## Full Usage Example

Run the interactive example with 11 demonstrations:

```bash
python -m ascetic_ddd.specification.domain.jsonpath.example_usage
```

The example demonstrates:
- All comparison operators (`==`, `!=`, `>`, `<`, `>=`, `<=`)
- Positional and named placeholders
- RFC 9535 logical operators (`&&`, `||`, `!`)
- Wildcard collections
- Lexer operation (tokenization)
- Specification reuse
- Boolean values

See the file `ascetic_ddd/specification/domain/jsonpath/examples/jsonpath_example.py` for the full code.

## Examples

### Basic Usage

```python
from ascetic_ddd.specification.domain.jsonpath.jsonpath_parser import parse

# Simple comparison
spec = parse("$[?@.age > %d]")
user = DictContext({"age": 30})
spec.match(user, (25,))  # True

# String comparison (RFC 9535: ==)
spec = parse("$[?@.status == %s]")
task = DictContext({"status": "done"})
spec.match(task, ("done",))  # True

# Named parameters
spec = parse("$[?@.score >= %(min_score)d]")
student = DictContext({"score": 85})
spec.match(student, {"min_score": 80})  # True

# Logical operators (RFC 9535)
spec = parse("$[?@.age > %d && @.active == %s]")
user = DictContext({"age": 30, "active": True})
spec.match(user, (25, True))  # True

# NOT operator (RFC 9535)
spec = parse("$[?!(@.deleted == %s)]")
item = DictContext({"deleted": False})
spec.match(item, (True,))  # True
```

### Working with Collections

```python
from ascetic_ddd.specification.domain.evaluate_visitor import CollectionContext

spec = parse("$.users[*][?(@.age >= %d)]")

user1 = DictContext({"name": "Alice", "age": 30})
user2 = DictContext({"name": "Bob", "age": 25})

users = CollectionContext([user1, user2])
root = DictContext({"users": users})

# Is there at least one user with age >= 28?
spec.match(root, (28,))  # True (Alice)
```

### Nested Wildcards

```python
from ascetic_ddd.specification.domain.evaluate_visitor import CollectionContext

# Nested wildcards: filtering by nested collections
spec = parse("$.categories[*][?@.items[*][?@.price > %f]]")

# Create structure: categories -> items
item1 = DictContext({"name": "Laptop", "price": 999.0})
item2 = DictContext({"name": "Mouse", "price": 29.0})
items1 = CollectionContext([item1, item2])
category1 = DictContext({"name": "Electronics", "items": items1})

item3 = DictContext({"name": "Shirt", "price": 49.0})
items2 = CollectionContext([item3])
category2 = DictContext({"name": "Clothing", "items": items2})

categories = CollectionContext([category1, category2])
store = DictContext({"categories": categories})

# Is there a category with an item costing more than 500?
spec.match(store, (500.0,))  # True (category1 has Laptop)
```

**Nested wildcards with logic:**

```python
# Nested wildcard with AND operator
spec = parse("$.categories[*][?@.items[*][?@.price > %f && @.price < %f]]")

# Is there a category with an item in the 500-1000 range?
spec.match(store, (500.0, 1000.0))  # True (Laptop: 999)

# Is there a category with an item in the 1000-2000 range?
spec.match(store, (1000.0, 2000.0))  # False
```

**Multiple matches:**

```python
# Check for multiple categories with expensive items
spec = parse("$.categories[*][?@.items[*][?@.price > %f]]")

# Category 1 with expensive item
item1 = DictContext({"name": "Laptop", "price": 999.0})
items1 = CollectionContext([item1])
category1 = DictContext({"name": "Electronics", "items": items1})

# Category 2 with expensive item
item2 = DictContext({"name": "Designer Jeans", "price": 299.0})
items2 = CollectionContext([item2])
category2 = DictContext({"name": "Clothing", "items": items2})

categories = CollectionContext([category1, category2])
store = DictContext({"categories": categories})

# Both categories have items costing more than 200
spec.match(store, (200.0,))  # True
```

### Nested Paths

```python
# Create a special context for nested structures
class NestedDictContext:
    def __init__(self, data):
        self._data = data

    def get(self, key):
        value = self._data[key]
        # Automatically wrap nested dicts
        if isinstance(value, dict):
            return NestedDictContext(value)
        return value

# Simple nested path: $.store.products[*][?@.price > 500]
spec = parse("$.store.products[*][?@.price > %f]")

product1 = DictContext({"name": "Laptop", "price": 999.0})
product2 = DictContext({"name": "Mouse", "price": 29.0})
products = CollectionContext([product1, product2])

data = NestedDictContext({
    "store": {
        "name": "MyStore",
        "products": products
    }
})

spec.match(data, (500.0,))  # True (Laptop > 500)
```

**Deeply nested paths:**

```python
# Deep nesting: $.company.department.team.members[*][?@.age > 28]
spec = parse("$.company.department.team.members[*][?@.age > %d]")

member1 = DictContext({"name": "Alice", "age": 30})
member2 = DictContext({"name": "Bob", "age": 25})
members = CollectionContext([member1, member2])

data = NestedDictContext({
    "company": {
        "department": {
            "team": {
                "members": members
            }
        }
    }
})

spec.match(data, (28,))  # True (Alice > 28)
```

**Nested paths in filters:**

```python
# Filter on nested field: $[?@.user.profile.age > 25]
spec = parse("$[?@.user.profile.age > %d]")

data = NestedDictContext({
    "user": {
        "profile": {
            "age": 30
        }
    }
})

spec.match(data, (25,))  # True
```

**Combining nested paths and logic:**

```python
# $.store.products[*][?@.price > 500 && @.stock > 5]
spec = parse("$.store.products[*][?@.price > %f && @.stock > %d]")

product = DictContext({"name": "Monitor", "price": 599.0, "stock": 10})
products = CollectionContext([product])

data = NestedDictContext({
    "store": {
        "products": products
    }
})

spec.match(data, (500.0, 5))  # True
```

## Internals

### Tokens

The lexer recognizes the following token types:

```python
DOLLAR      # $
AT          # @
DOT         # .
LBRACKET    # [
RBRACKET    # ]
LPAREN      # (
RPAREN      # )
QUESTION    # ?
WILDCARD    # *
AND         # && (RFC 9535)
OR          # || (RFC 9535)
NOT         # ! (RFC 9535)
EQ          # == (RFC 9535: double sign)
NE/GT/LT/GTE/LTE  # Comparison operators
NUMBER      # 123, 45.67
STRING      # "text", 'text'
PLACEHOLDER # %d, %s, %(name)d
IDENTIFIER  # age, name, status
```

### AST Nodes

The parser creates the following Specification nodes:

- `GlobalScope()` - root context
- `Item()` - current collection element (@)
- `Field(parent, name)` - field access
- `Value(val)` - literal value
- `Equal/NotEqual/GreaterThan/...` - comparison operators
- `And(left, right)` - logical AND (&&)
- `Or(left, right)` - logical OR (||)
- `Not(operand)` - logical NOT (!)
- `Wildcard(parent, predicate)` - collection filtering
