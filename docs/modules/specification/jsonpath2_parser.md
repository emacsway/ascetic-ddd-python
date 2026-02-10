```{index} JSONPath2, JSONPath, Specification Pattern
```

# JSONPath2 Specification Parser

JSONPath expression parser for the Specification Pattern using the **jsonpath2** library.

## Description

This implementation uses the `jsonpath2` library to parse JSONPath expressions and converts them into Specification Pattern AST nodes. Supports C-style string formatting parameterization.

## Key Advantages

- **Uses jsonpath2** - a proven library for JSONPath parsing
- **Parameterization** - placeholder support (%s, %d, %f, %(name)s)
- **Comparison operators** - `=`, `!=`, `>`, `<`, `>=`, `<=`
- **Wildcard collections** - filtering collection elements
- **Nested wildcards** - filtering by nested collections (`$.categories[*][?@.items[*][?@.price > 100]]`)
- **Nested paths** - support for `@.profile.age`, `@.company.department.manager.level`
- **Parentheses grouping** - automatic parentheses insertion for filters
- **Reusability** - one specification with different parameters
- **Full feature parity** - fully compatible with other parser versions

## Usage

```python
from ascetic_ddd.specification.domain.jsonpath.jsonpath2_parser import parse

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

## Supported Features

### Comparison Operators
- `=` - Equal (jsonpath2 uses single `=`, not `==`)
- `!=` - Not equal
- `>` - Greater than
- `<` - Less than
- `>=` - Greater than or equal
- `<=` - Less than or equal

### Parameterization
```python
# Positional
parse("$[?(@.age > %d)]")          # Integer
parse("$[?(@.name = %s)]")          # String
parse("$[?(@.price > %f)]")         # Floating point number

# Named
parse("$[?(@.age > %(min_age)d)]")
parse("$[?(@.name = %(name)s)]")
```

### Wildcard Collections
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

## jsonpath2 Specifics

### Syntax

The jsonpath2 library **deviates from the RFC 9535 standard**:

- **Both variants supported**: `=` and `==` for equality
  - **RFC 9535 standard** defines `==` for equality
  - **jsonpath2 library** deviates from the standard and uses `=`
  - Our parser automatically normalizes `==` → `=` for library compatibility
  - This provides better UX and compatibility with Native parsers

- **Logical operators are fully supported!**
  - **RFC 9535 standard** uses: `&&` (AND), `||` (OR), `!` (NOT)
  - **jsonpath2 library** uses: `and`, `or`, `not` (text operators)
  - Our parser automatically normalizes: `&&` → `and`, `||` → `or`, `!` → `not`
  - **Full RFC 9535 syntax support!**

- **Automatic parentheses insertion in filters**
  - **jsonpath2 library** requires parentheses around conditions: `$[?(@.age > 25)]`
  - Our parser automatically adds parentheses if they are missing
  - You can write: `$[?@.age > 25]` → automatically converted to `$[?(@.age > 25)]`

- Strict syntax validation with detailed error messages

### Advantages

1. **Performance** - optimized ANTLR-based parser

### Limitations (deviations from RFC 9535)

1. **Equality syntax** - uses `=` instead of the standard `==`
   - Our enhancement adds `==` support via automatic normalization
2. **Parentheses required** - filters require parentheses around conditions
   - Our enhancement automatically adds parentheses
3. **Strict validation** - stricter syntax requirements

Thanks to our enhancements (automatic syntax normalization), most limitations are hidden from the user.

## Nested Path Support

The JSONPath2 parser supports nested paths in filters, allowing access to fields of nested objects:

### Nested Path Syntax

```python
# Simple nested path
spec = parse("$[?(@.profile.age > %d)]")

# Deep nesting
spec = parse("$[?(@.company.department.manager.level >= %d)]")

# Nested paths in compound conditions
spec = parse("$[?(@.profile.age > %d && @.profile.status = %s)]")
```

### Nested Path Examples

```python
from ascetic_ddd.specification.domain.jsonpath.jsonpath2_parser import parse

# Context class with nested object support
class NestedDictContext:
    def __init__(self, data):
        self._data = data

    def get(self, key):
        value = self._data[key]
        # Automatically wrap nested dicts
        if isinstance(value, dict):
            return NestedDictContext(value)
        return value

# Simple nested path
spec = parse("$[?(@.profile.age > %d)]")
user = NestedDictContext({
    "name": "Alice",
    "profile": {"age": 30, "city": "NYC"}
})
spec.match(user, (25,))  # True

# Deep nesting (3+ levels)
spec = parse("$[?(@.company.department.manager.level >= %d)]")
employee = NestedDictContext({
    "name": "Bob",
    "company": {
        "name": "TechCorp",
        "department": {
            "name": "Engineering",
            "manager": {"name": "Charlie", "level": 5}
        }
    }
})
spec.match(employee, (3,))  # True

# Nested paths in compound conditions
spec = parse("$[?(@.profile.age > %d && @.profile.status = %s)]")
user = NestedDictContext({
    "name": "Diana",
    "profile": {"age": 28, "status": "active"}
})
spec.match(user, (25, "active"))  # True

# Named parameters with nested paths
spec = parse("$[?(@.settings.notifications.email = %(enabled)s)]")
user = NestedDictContext({
    "name": "Eve",
    "settings": {
        "notifications": {"email": True, "sms": False}
    }
})
spec.match(user, {"enabled": True})  # True
```

### Important Notes

1. **Automatic chain handling**: The parser automatically recognizes and processes nested paths of any depth

2. **Context requirements**: The context must return nested objects that also support the `get()` protocol:
   ```python
   class NestedDictContext:
       def get(self, key):
           value = self._data[key]
           if isinstance(value, dict):
               return NestedDictContext(value)  # Important!
           return value
   ```

3. **Compatibility**: The syntax is fully compatible with RFC 9535 and other parsers

## Examples

### Basic Usage

```python
from ascetic_ddd.specification.domain.jsonpath.jsonpath2_parser import parse

# Simple comparison
spec = parse("$[?(@.age > %d)]")
user = DictContext({"age": 30})
spec.match(user, (25,))  # True

# String comparison
spec = parse("$[?(@.status = %s)]")
task = DictContext({"status": "done"})
spec.match(task, ("done",))  # True

# Named parameters
spec = parse("$[?(@.score >= %(min_score)d)]")
student = DictContext({"score": 85})
spec.match(student, {"min_score": 80})  # True
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

The JSONPath2 parser supports nested wildcards for filtering by nested collections:

```python
from ascetic_ddd.specification.domain.evaluate_visitor import CollectionContext

# Nested wildcards: filtering by nested collections
spec = parse("$.categories[*][?@.items[*][?@.price > %f]]")

# Create data structure
item1 = DictContext({"name": "Laptop", "price": 999.0})
item2 = DictContext({"name": "Mouse", "price": 29.0})
items1 = CollectionContext([item1, item2])
category1 = DictContext({"name": "Electronics", "items": items1})

item3 = DictContext({"name": "Shirt", "price": 49.0})
items2 = CollectionContext([item3])
category2 = DictContext({"name": "Clothing", "items": items2})

categories = CollectionContext([category1, category2])
store = DictContext({"categories": categories})

# Is there at least one category with an item costing more than 500?
spec.match(store, (500.0,))  # True (Laptop)
```

**Nested wildcards with logic:**

```python
# Combining conditions in nested filters
spec = parse("$.categories[*][?@.items[*][?@.price > %f && @.price < %f]]")

item1 = DictContext({"name": "Monitor", "price": 599.0})
items = CollectionContext([item1])
category = DictContext({"name": "Displays", "items": items})
categories = CollectionContext([category])
store = DictContext({"categories": categories})

# Category with an item in the price range
spec.match(store, (500.0, 700.0))  # True
```

**With named parameters:**

```python
spec = parse("$.categories[*][?@.items[*][?@.price > %(min_price)f]]")
spec.match(store, {"min_price": 500.0})  # True
```

## Testing

```bash
# Run jsonpath2 parser tests
python -m unittest ascetic_ddd.specification.domain.jsonpath.test_jsonpath_parser_jsonpath2 -v

# All tests
python -m unittest discover -s ascetic_ddd/specification -p "test_*.py" -v
```
