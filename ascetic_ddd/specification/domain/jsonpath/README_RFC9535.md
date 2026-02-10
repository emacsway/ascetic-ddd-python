# JSONPath RFC 9535 Specification Parser

JSONPath expression parser for the Specification Pattern using the **jsonpath-rfc9535** library.

## Description

This implementation uses the `jsonpath-rfc9535` library to parse JSONPath expressions and converts them into Specification Pattern AST nodes. **Fully compliant with the RFC 9535 standard** and supports C-style string formatting parameterization.

## Key Advantages

- **Full RFC 9535 compliance** - uses the official JSONPath standard
- **Parameterization** - placeholder support (%s, %d, %f, %(name)s)
- **Standard operators** - `==`, `!=`, `>`, `<`, `>=`, `<=`
- **RFC 9535 logical operators** - `&&` (AND), `||` (OR), `!` (NOT)
- **Parentheses** - logical expression grouping (`$[?(@.age >= 18 && @.age <= 65) && @.active == true]`)
- **Wildcard collections** - filtering collection elements
- **Nested wildcards** - filtering by nested collections (`$.categories[*][?@.items[*][?@.price > 100]]`)
- **Nested paths** - access to nested fields (`$[?@.profile.age > 25]`, `$[?@.company.department.manager.level > 5]`)
- **Reusability** - one specification with different parameters
- **Strict standard compliance** - guaranteed compatibility

## Usage

```python
from ascetic_ddd.specification.domain.jsonpath.jsonpath_rfc9535_parser import parse

# Create specification
spec = parse("$[?@.age > %d]")


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

## RFC 9535 Compliance

This implementation is **fully compliant** with the RFC 9535 standard:

### Comparison Operators (RFC 9535)
- `==` - Equal (**double sign**, as per the standard)
- `!=` - Not equal
- `>` - Greater than
- `<` - Less than
- `>=` - Greater than or equal
- `<=` - Less than or equal

### Logical Operators (RFC 9535)
- `&&` - Logical AND (as per the standard)
- `||` - Logical OR (as per the standard)
- `!` - Logical NOT (as per the standard)

### References
- `@` - Current node
- `$` - Root node

## Supported Features

### Comparison Operators

```python
# RFC 9535 uses == for equality (double sign)
parse("$[?@.age == %d]")           # Equal
parse("$[?@.age != %d]")           # Not equal
parse("$[?@.age > %d]")            # Greater than
parse("$[?@.age < %d]")            # Less than
parse("$[?@.age >= %d]")           # Greater than or equal
parse("$[?@.age <= %d]")           # Less than or equal
```

### Logical Operators

```python
# RFC 9535 uses && for AND
parse("$[?@.age > %d && @.active == %s]")

# RFC 9535 uses || for OR
parse("$[?@.age < %d || @.age > %d]")

# RFC 9535 uses ! for NOT
parse("$[?!(@.active == %s)]")

# Complex expressions
parse("$[?(@.age >= %d && @.age <= %d) && @.status == %s]")
```

### Parameterization

```python
# Positional parameters
parse("$[?@.age > %d]")            # Integer
parse("$[?@.name == %s]")          # String
parse("$[?@.price > %f]")          # Floating point number

# Named parameters
parse("$[?@.age > %(min_age)d]")
parse("$[?@.name == %(name)s]")
parse("$[?@.price > %(min_price)f]")

# Multiple parameters
parse("$[?@.age >= %(min_age)d && @.age <= %(max_age)d]")
```

### Wildcard Collections

```python
spec = parse("$.items[*][?@.price > %f]")

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

## Examples

### Basic Usage

```python
from ascetic_ddd.specification.domain.jsonpath.jsonpath_rfc9535_parser import parse

# Simple comparison (RFC 9535: ==)
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
```

### Logical Operators (RFC 9535)

```python
# AND operator (RFC 9535: &&)
spec = parse("$[?@.age > %d && @.active == %s]")
user = DictContext({"age": 30, "active": True})
spec.match(user, (25, True))  # True

# OR operator (RFC 9535: ||)
spec = parse("$[?@.age < %d || @.age > %d]")
user_young = DictContext({"age": 15})
spec.match(user_young, (18, 65))  # True

# NOT operator (RFC 9535: !)
spec = parse("$[?!(@.active == %s)]")
user_inactive = DictContext({"active": False})
spec.match(user_inactive, (True,))  # True
```

### Working with Collections

```python
from ascetic_ddd.specification.domain.evaluate_visitor import CollectionContext

spec = parse("$.users[*][?@.age >= %d]")

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

# Add an expensive item to the second category
item4 = DictContext({"name": "Designer Jeans", "price": 299.0})
items2 = CollectionContext([item3, item4])
category2 = DictContext({"name": "Clothing", "items": items2})

categories = CollectionContext([category1, category2])
store = DictContext({"categories": categories})

# Now both categories have items costing more than 200
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

# Simple nested path: $[?@.profile.age > 25]
spec = parse("$[?@.profile.age > %d]")

data = NestedDictContext({
    "profile": {
        "age": 30,
        "name": "Alice"
    }
})

spec.match(data, (25,))  # True
```

**Deeply nested paths:**

```python
# Deep nesting: $[?@.company.department.manager.level > 5]
spec = parse("$[?@.company.department.manager.level > %d]")

data = NestedDictContext({
    "company": {
        "department": {
            "manager": {
                "level": 7,
                "name": "Alice"
            }
        }
    }
})

spec.match(data, (5,))  # True
```

**Nested paths with logical operators:**

```python
# $[?@.profile.age > 25 && @.profile.active == true]
spec = parse("$[?@.profile.age > %d && @.profile.active == %s]")

data = NestedDictContext({
    "profile": {
        "age": 30,
        "active": True
    }
})

spec.match(data, (25, True))  # True
```

**Nested paths with parentheses:**

```python
# Parentheses for operator precedence
spec = parse("$[?(@.profile.age >= %d && @.profile.age <= %d) && @.profile.active == %s]")

data = NestedDictContext({
    "profile": {
        "age": 30,
        "active": True
    }
})

spec.match(data, (25, 35, True))  # True
```

### Complex Expressions

```python
# Combining operators
spec = parse("$[?(@.age >= %d && @.age <= %d) && @.status == %s]")
user = DictContext({"age": 30, "status": "active"})
spec.match(user, (25, 35, "active"))  # True

# Multiple named parameters
spec = parse("$[?@.age >= %(min_age)d && @.age <= %(max_age)d]")
user = DictContext({"age": 30})
spec.match(user, {"min_age": 25, "max_age": 35})  # True
```

## Testing

```bash
# Run RFC 9535 parser tests
python -m unittest ascetic_ddd.specification.domain.jsonpath.test_jsonpath_parser_rfc9535 -v

# Run examples
python ascetic_ddd/specification/domain/jsonpath/example_usage_rfc9535.py

# All tests
python -m unittest discover -s ascetic_ddd/specification -p "test_*.py" -v
```

## Advantages of RFC 9535

1. **Standard compliance** - full compatibility with RFC 9535
2. **Official specification** - based on the official IETF standard
3. **Portability** - easily integrates with other RFC 9535 systems
4. **Stability** - the standard ensures long-term stability
5. **Clear syntax** - `==` for equality, `&&`/`||` for logic
6. **Active support** - the jsonpath-rfc9535 library is actively maintained

## Dependencies

- `jsonpath-rfc9535` - JSONPath expression parsing (RFC 9535 compliant)
- Modules from `ascetic_ddd.specification.domain`:
  - `nodes` - Specification AST nodes
  - `evaluate_visitor` - Specification evaluation

## Installation

```bash
pip install jsonpath-rfc9535
```

