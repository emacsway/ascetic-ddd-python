"""PostgreSQL visitor for generating SQL from specification AST."""
import inflection
from typing import Any, Callable, Dict, List, Optional, Tuple

from ascetic_ddd.specification.domain.nodes import (
    Visitor,
    Collection,
    Field,
    GlobalScope,
    Infix,
    Item,
    Object,
    Operable,
    Prefix,
    Postfix,
    Value,
    Visitable,
    EmptiableObject,
    extract_field_path,
)
from ascetic_ddd.specification.domain.constants import OPERATOR

from ascetic_ddd.specification.infrastructure.transform_visitor import ITransformContext, TransformVisitor
from ascetic_ddd.specification.infrastructure.schema import SchemaRegistry


def compile_specification(
    context: ITransformContext, expression: Visitable
) -> Tuple[str, List[Any]]:
    """
    Compile a domain specification to SQL.

    Args:
        context: Transform context for mapping domain to infrastructure
        expression: Domain specification expression

    Returns:
        Tuple of (sql_string, parameters)
    """
    # First, transform domain expression to infrastructure expression
    transform_visitor = TransformVisitor(context)
    expression.accept(transform_visitor)
    infrastructure_expr = transform_visitor.result()

    # Then, generate SQL from infrastructure expression
    postgresql_visitor = PostgresqlVisitor()
    infrastructure_expr.accept(postgresql_visitor)
    return postgresql_visitor.result()


def compile_to_sql(
    expression: Visitable,
    schema: Optional[SchemaRegistry] = None
) -> Tuple[str, List[Any]]:
    """
    Compile AST directly to SQL without context transformation.

    Useful for generated code where AST is already in the right form.

    Args:
        expression: Specification expression AST
        schema: Optional schema registry for relational collection support

    Returns:
        Tuple of (sql_string, parameters)
    """
    postgresql_visitor = PostgresqlVisitor(schema=schema)
    expression.accept(postgresql_visitor)
    return postgresql_visitor.result()


class PostgresqlVisitor(Visitor):
    """
    Visitor that generates PostgreSQL SQL from specification AST.

    Handles:
    - Field path rendering (e.g., "something.tenant_id")
    - Parameterized value placeholders ($1, $2, ...)
    - Operator precedence with automatic parenthesization
    - Prefix operators (NOT, unary +/-)
    - Infix operators (AND, OR, =, <, >, etc.)
    - Collection/Wildcard operators with embedded (unnest) and relational (EXISTS) modes
    """

    def __init__(
        self,
        placeholder_index: int = 0,
        schema: Optional[SchemaRegistry] = None
    ):
        self._sql = ""
        self._placeholder_index = placeholder_index
        self._parameters: List[Any] = []
        self._precedence = 0
        self._precedence_mapping: Dict[str, int] = {}
        self._setup_precedence()
        # Wildcard context tracking
        self._in_wildcard = False
        self._wildcard_alias = ""
        self._wildcard_counter = 0
        # Schema registry for relational collections
        self._schema = schema

    def _setup_precedence(self) -> None:
        """
        Setup PostgreSQL operator precedence.

        Based on: https://www.postgresql.org/docs/14/sql-syntax-lexical.html#SQL-PRECEDENCE-TABLE
        """
        # Higher numbers = higher precedence
        self._set_precedence(160, ". LEFT", ":: LEFT")
        self._set_precedence(150, "[ LEFT")
        self._set_precedence(140, "+ RIGHT", "- RIGHT")
        self._set_precedence(130, "^ LEFT")
        self._set_precedence(120, "* LEFT", "/ LEFT", "% LEFT")
        self._set_precedence(110, "+ LEFT", "- LEFT")
        # All other native and user-defined operators
        self._set_precedence(100, "(any other operator) LEFT")
        self._set_precedence(
            90, "BETWEEN NON", "IN NON", "LIKE NON", "ILIKE NON", "SIMILAR NON"
        )
        self._set_precedence(
            80, "< NON", "> NON", "= NON", "<= NON", ">= NON", "!= NON"
        )
        self._set_precedence(70, "IS NON", "ISNULL NON", "NOTNULL NON")
        self._set_precedence(60, "NOT RIGHT")
        self._set_precedence(50, "AND LEFT")
        self._set_precedence(40, "OR LEFT")

    def _set_precedence(self, precedence: int, *operators: str) -> None:
        """Set precedence for given operators."""
        for op in operators:
            self._precedence_mapping[op] = precedence

    def _get_node_precedence_key(self, node: Operable) -> str:
        """Get precedence key for an operable node."""
        operator = node.operator()
        associativity = node.associativity()
        return f"{operator} {associativity}"

    def _visit(self, precedence_key: str, callable_fn: Callable[[], None]) -> None:
        """
        Visit with precedence handling.

        Automatically adds parentheses if inner precedence is lower than outer.
        """
        outer_precedence = self._precedence
        inner_precedence = self._precedence_mapping.get(
            precedence_key,
            self._precedence_mapping.get("(any other operator) LEFT", outer_precedence),
        )

        self._precedence = inner_precedence

        # Add opening parenthesis if needed
        if inner_precedence < outer_precedence:
            self._sql += "("

        callable_fn()

        # Add closing parenthesis if needed
        if inner_precedence < outer_precedence:
            self._sql += ")"

        self._precedence = outer_precedence

    def visit_global_scope(self, node: GlobalScope) -> None:
        """Visit global scope node."""
        pass

    def visit_object(self, node: Object) -> None:
        """Visit object node."""
        pass

    def visit_collection(self, node: Collection) -> None:
        """
        Visit collection node (Wildcard).

        Two modes:
        1. Embedded (JSONB/array): EXISTS (SELECT 1 FROM unnest(collection) AS item WHERE predicate)
        2. Relational (separate table): EXISTS (SELECT 1 FROM table AS item WHERE fk_conditions AND predicate)
        """
        # Extract collection name for alias and schema lookup
        collection_name = self._extract_collection_name(node)
        field_name = self._extract_field_name(node)

        # Check if this is a relational collection
        if self._schema is not None and self._schema.is_relational(field_name):
            self._visit_relational_collection(node, field_name, collection_name)
        else:
            # Default: embedded collection (JSONB/array)
            self._visit_embedded_collection(node, collection_name)

    def _visit_embedded_collection(self, node: Collection, collection_name: str) -> None:
        """Generate SQL for JSONB/array collections using unnest."""
        # Extract collection path (e.g., "Items" from Object(GlobalScope(), "Items"))
        collection_path = self._extract_collection_path(node)

        # Generate unique alias for this wildcard
        self._wildcard_counter += 1
        alias = f"{collection_name.lower()}_{self._wildcard_counter}"

        # Save context
        outer_in_wildcard = self._in_wildcard
        outer_wildcard_alias = self._wildcard_alias

        # Enter wildcard context
        self._in_wildcard = True
        self._wildcard_alias = alias

        # Generate EXISTS subquery with unnest
        self._sql += "EXISTS (SELECT 1 FROM unnest("
        self._sql += collection_path
        self._sql += ") AS "
        self._sql += alias
        self._sql += " WHERE "

        # Visit predicate
        node.predicate().accept(self)

        self._sql += ")"

        # Restore context
        self._in_wildcard = outer_in_wildcard
        self._wildcard_alias = outer_wildcard_alias

    def _visit_relational_collection(
        self,
        node: Collection,
        field_name: str,
        collection_name: str
    ) -> None:
        """Generate SQL for collections in separate tables."""
        mapping = self._schema.get(field_name)
        if mapping is None:
            # Fallback to embedded if no mapping found
            self._visit_embedded_collection(node, collection_name)
            return

        # Generate unique alias for this wildcard
        self._wildcard_counter += 1
        alias = mapping.alias if mapping.alias else collection_name.lower()
        alias = f"{alias}_{self._wildcard_counter}"

        # Save context BEFORE determining parent ref
        outer_in_wildcard = self._in_wildcard
        outer_wildcard_alias = self._wildcard_alias

        # Determine parent reference BEFORE entering new context
        parent_ref = self._get_parent_ref_for_relational(
            outer_in_wildcard, outer_wildcard_alias
        )

        # Enter wildcard context
        self._in_wildcard = True
        self._wildcard_alias = alias

        # Generate EXISTS subquery with JOIN conditions
        self._sql += "EXISTS (SELECT 1 FROM "
        self._sql += mapping.table
        self._sql += " AS "
        self._sql += alias
        self._sql += " WHERE "

        # Generate FK conditions (supports composite keys)
        for i, fk in enumerate(mapping.foreign_keys):
            if i > 0:
                self._sql += " AND "
            self._sql += alias
            self._sql += "."
            self._sql += fk.child_column
            self._sql += " = "
            self._sql += parent_ref
            self._sql += "."
            self._sql += fk.parent_column

        # Add predicate
        self._sql += " AND "

        # Visit predicate
        node.predicate().accept(self)

        self._sql += ")"

        # Restore context
        self._in_wildcard = outer_in_wildcard
        self._wildcard_alias = outer_wildcard_alias

    def _get_parent_ref_for_relational(
        self,
        outer_in_wildcard: bool,
        outer_wildcard_alias: str
    ) -> str:
        """
        Return parent reference using saved context.

        Called BEFORE entering new wildcard context to get the correct outer reference.
        """
        # If we were in a nested wildcard, use the outer wildcard alias
        if outer_in_wildcard and outer_wildcard_alias:
            return outer_wildcard_alias

        # Otherwise, use schema's parent reference
        if self._schema is not None:
            return self._schema.get_parent_ref()

        return ""

    def _extract_field_name(self, node: Collection) -> str:
        """Extract the field name from collection's parent Object."""
        parent = node.parent()
        if not parent.is_root():
            return parent.name()
        return ""

    def _extract_collection_path(self, node: Collection) -> str:
        """Extract the SQL path to a collection from a CollectionNode."""
        parts: List[str] = []

        # Walk up the parent chain to collect path components
        parent = node.parent()
        while not parent.is_root():
            parts.insert(0, parent.name())
            parent = parent.parent()

        # If we're in a wildcard context and the root parent is Item(), prefix with current alias
        # This handles nested wildcards: category_1.Items instead of just Items
        if self._in_wildcard and self._is_item_reference(parent):
            if parts:
                return self._wildcard_alias + "." + ".".join(parts)
            return self._wildcard_alias

        return ".".join(parts)

    def _extract_collection_name(self, node: Collection) -> str:
        """
        Extract the collection name for alias generation.

        e.g., "Items" -> "Item", "Categories" -> "Category"
        """
        parent = node.parent()
        if not parent.is_root():
            return inflection.singularize(parent.name())
        return "item"  # fallback

    def _is_item_reference(self, obj: EmptiableObject) -> bool:
        """Check if the object is Item() (current item in wildcard)."""
        return isinstance(obj, Item)

    def visit_item(self, node: Item) -> None:
        """
        Visit item node.

        Item() in wildcard context refers to the current item alias.
        This is handled in visit_field when we detect Item() as parent.
        """
        pass

    def visit_field(self, node: Field) -> None:
        """
        Visit field node and render as SQL field path.

        Handles both normal field access and item references in wildcard context.
        """
        # Check if this field references an item in a wildcard context
        if self._in_wildcard and self._is_item_reference(node.object()):
            # This is a field of the current item: item.Price, item.Active, etc.
            self._sql += self._wildcard_alias
            self._sql += "."
            self._sql += node.name()
        else:
            # Normal field access
            path = extract_field_path(node)
            name = ".".join(path)
            self._sql += name

    def visit_value(self, node: Value) -> None:
        """
        Visit value node and add parameterized placeholder.

        Adds parameter to list and renders as $N placeholder.
        """
        val = node.value()
        self._parameters.append(val)
        self._sql += f"${len(self._parameters)}"

    def visit_prefix(self, node: Prefix) -> None:
        """
        Visit prefix node (e.g., NOT, unary +/-).

        Handles precedence and renders operator before operand.
        """
        precedence_key = self._get_node_precedence_key(node)

        def visit_fn():
            operator = node.operator()
            # Unary +/- don't need space
            if operator in (OPERATOR.POS, OPERATOR.NEG):
                self._sql += str(operator.value)
            else:
                self._sql += f"{operator.value} "
            node.operand().accept(self)

        self._visit(precedence_key, visit_fn)

    def visit_infix(self, node: Infix) -> None:
        """
        Visit infix node (e.g., AND, OR, =, <, >).

        Handles precedence and renders: left operator right
        """
        precedence_key = self._get_node_precedence_key(node)

        def visit_fn():
            node.left().accept(self)
            self._sql += f" {node.operator().value} "
            node.right().accept(self)

        self._visit(precedence_key, visit_fn)

    def visit_postfix(self, node: Postfix) -> None:
        """
        Visit postfix node (e.g., IS NULL).

        Handles precedence and renders operand before operator.
        """
        precedence_key = self._get_node_precedence_key(node)

        def visit_fn():
            node.operand().accept(self)
            self._sql += f" {node.operator().value}"

        self._visit(precedence_key, visit_fn)

    def result(self) -> Tuple[str, List[Any]]:
        """
        Return the generated SQL and parameters.

        Returns:
            Tuple of (sql_string, parameter_list)
        """
        return self._sql, self._parameters
