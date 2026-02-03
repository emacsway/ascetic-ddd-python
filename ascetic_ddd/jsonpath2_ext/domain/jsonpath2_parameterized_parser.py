"""
Extension for jsonpath2 parser to support parameterized expressions.

Extends the parser to recognize placeholders (%s, %d, %f, %(name)s)
and bind values at execution time.
"""
import copy
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from jsonpath2.node import MatchData
from jsonpath2.path import Path


# Unique placeholder markers (chosen to avoid collision with real data)
PLACEHOLDER_MARKER_INT = -8765432109876
PLACEHOLDER_MARKER_FLOAT = -8765432109876.5
PLACEHOLDER_MARKER_STR = "__JSONPATH2_PARAM_PLACEHOLDER_x9y8z7__"

# Pre-compiled regex patterns for better performance
_NAMED_PLACEHOLDER_PATTERN = re.compile(r'%\((\w+)\)([sdf])')
_POSITIONAL_PLACEHOLDER_PATTERN = re.compile(r'%([sdf])')
_FILTER_WITHOUT_PARENS_PATTERN = re.compile(r'\[\?(?!\()')


class JSONPath2ParameterError(Exception):
    """Base exception for JSONPath2 parameter binding errors."""
    pass


class MissingParameterError(JSONPath2ParameterError):
    """Raised when a required parameter is missing."""

    def __init__(
        self, message: str, param_name: Optional[str] = None, param_index: Optional[int] = None
    ):
        super().__init__(message)
        self.param_name = param_name
        self.param_index = param_index


@dataclass(frozen=True)
class PlaceholderInfo:
    """Information about a placeholder in the template."""
    original: str
    name: str
    format_type: str
    positional: bool


@dataclass
class PlaceholderReference:
    """
    Reference to a placeholder location in the AST.

    Stores where a placeholder is located so we can update it when binding parameters.
    """
    expression: Any
    attribute: str
    name: str
    format_type: str

    def bind(self, value: Any) -> None:
        """Bind a value to this placeholder by updating the AST."""
        setattr(self.expression, self.attribute, value)


def _iterate_with_string_awareness(template: str) -> Iterator[Tuple[int, str, bool]]:
    """
    Iterate through template tracking string literal context.

    Yields:
        Tuples of (index, char, in_string)
    """
    in_string = False
    string_char: Optional[str] = None
    i = 0

    while i < len(template):
        char = template[i]

        # Track string literals (handling escaped quotes)
        if char in ('"', "'") and (i == 0 or template[i - 1] != '\\'):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None

        yield i, char, in_string
        i += 1


def _get_placeholder_marker(format_type: str) -> str:
    """
    Get the appropriate placeholder marker string for a format type.

    Args:
        format_type: 's', 'd', or 'f'

    Returns:
        String representation of the marker for use in JSONPath
    """
    if format_type == 's':
        return f'"{PLACEHOLDER_MARKER_STR}"'
    elif format_type == 'd':
        return str(PLACEHOLDER_MARKER_INT)
    elif format_type == 'f':
        return str(PLACEHOLDER_MARKER_FLOAT)
    else:
        raise ValueError(f"Unknown format type: {format_type}")


def _is_placeholder_marker(value: Any, format_type: str) -> bool:
    """
    Check if a value matches a placeholder marker.

    Args:
        value: The value to check
        format_type: Expected format type ('s', 'd', 'f')

    Returns:
        True if value is the marker for the given format type
    """
    if format_type == 's':
        return value == PLACEHOLDER_MARKER_STR
    elif format_type == 'd':
        return value == PLACEHOLDER_MARKER_INT
    elif format_type == 'f':
        # Float marker might be parsed as int or float
        return value in (PLACEHOLDER_MARKER_FLOAT, PLACEHOLDER_MARKER_INT)
    return False


class ParametrizedPath:
    """
    JSONPath with placeholder support.

    Parses template once, binds different values at execution time.
    Thread-safe: creates a copy of AST for each execution.
    """

    def __init__(self, template: str):
        """
        Parse template with placeholders.

        Args:
            template: JSONPath with %s, %d, %f or %(name)s placeholders
        """
        self.template = template
        self._placeholder_info: List[PlaceholderInfo] = []

        # Parse template and replace placeholders with markers
        processed_template = self._preprocess_template(template)

        # Parse with jsonpath2 and cache the original AST
        self._path = Path.parse_str(processed_template)

    @property
    def placeholders(self) -> List[PlaceholderInfo]:
        """Return placeholder info for compatibility."""
        return self._placeholder_info

    def _normalize_equality_operator(self, template: str) -> str:
        """
        Normalize == to = for jsonpath2 library compatibility.

        RFC 9535 standard defines == for equality, but jsonpath2 library
        deviates from the standard and uses single =.
        This method provides better UX by accepting both syntaxes.

        Args:
            template: JSONPath template string

        Returns:
            Normalized template with == replaced by =
        """
        result: List[str] = []
        i = 0

        for idx, char, in_string in _iterate_with_string_awareness(template):
            if idx < i:
                continue
            i = idx

            # Replace == with = only outside strings
            if not in_string and char == '=' and i + 1 < len(template) and template[i + 1] == '=':
                result.append('=')
                i += 2
                continue

            result.append(char)
            i += 1

        return ''.join(result)

    def _normalize_logical_operators(self, template: str) -> str:
        """
        Normalize RFC 9535 logical operators to jsonpath2 text operators.

        RFC 9535 standard defines: &&, ||, !
        jsonpath2 library uses text operators: and, or, not
        This method normalizes symbol operators to text operators.

        Args:
            template: JSONPath template string

        Returns:
            Normalized template with text logical operators
        """
        result: List[str] = []
        i = 0

        while i < len(template):
            char = template[i]

            # Check if we're in a string
            in_string = False
            string_char: Optional[str] = None
            for j in range(i):
                c = template[j]
                if c in ('"', "'") and (j == 0 or template[j - 1] != '\\'):
                    if not in_string:
                        in_string = True
                        string_char = c
                    elif c == string_char:
                        in_string = False
                        string_char = None

            if not in_string:
                # Replace && with and
                if char == '&' and i + 1 < len(template) and template[i + 1] == '&':
                    result.append(' and ')
                    i += 2
                    continue

                # Replace || with or
                if char == '|' and i + 1 < len(template) and template[i + 1] == '|':
                    result.append(' or ')
                    i += 2
                    continue

                # Replace ! with not (but not in !=)
                if char == '!' and i + 1 < len(template) and template[i + 1] != '=':
                    # Special case: ?!(...) should become ?(not ...) not ?not (...)
                    if result and ''.join(result).rstrip().endswith('?'):
                        if i + 1 < len(template) and template[i + 1] == '(':
                            result.append('(not ')
                            i += 2
                            continue
                    result.append('not ')
                    i += 1
                    continue

            result.append(char)
            i += 1

        return ''.join(result)

    def _add_parentheses_to_filter(self, template: str) -> str:
        """
        Add parentheses around filter expressions if not present.

        jsonpath2 library requires parentheses: $[?(@.age > 25)] not $[?@.age > 25]
        RFC 9535 allows both syntaxes, so we normalize to jsonpath2 format.

        Args:
            template: JSONPath template string

        Returns:
            Template with parentheses added
        """
        result = template

        # Find all [?@ patterns that don't have ( after ?
        positions: List[int] = []
        for match in _FILTER_WITHOUT_PARENS_PATTERN.finditer(result):
            pos = match.end()
            if pos < len(result) and (
                result[pos] == '@' or
                (result[pos] == ' ' and pos + 1 < len(result) and result[pos + 1] == '@')
            ):
                positions.append(match.start())

        # Process from right to left to maintain positions
        for pos in reversed(positions):
            # Find the matching ]
            depth = 1
            i = pos + 2  # After [?
            closing_pos: Optional[int] = None

            while i < len(result) and depth > 0:
                if result[i] == '[':
                    depth += 1
                elif result[i] == ']':
                    depth -= 1
                    if depth == 0:
                        closing_pos = i
                        break
                i += 1

            if closing_pos is not None:
                # Insert ) before ]
                result = result[:closing_pos] + ')' + result[closing_pos:]
                # Insert ( after ?
                insert_pos = pos + 2  # After [?
                result = result[:insert_pos] + '(' + result[insert_pos:]

        return result

    def _preprocess_template(self, template: str) -> str:
        """
        Replace placeholders with temporary markers and normalize operators.

        Args:
            template: Original template with placeholders

        Returns:
            Processed template with markers
        """
        # Add parentheses to filter expressions (required by jsonpath2)
        processed = self._add_parentheses_to_filter(template)

        # Normalize == to = for jsonpath2 library compatibility
        processed = self._normalize_equality_operator(processed)

        # Normalize logical operators for jsonpath2 library compatibility
        processed = self._normalize_logical_operators(processed)

        # Find and replace named placeholders: %(name)s, %(age)d, %(price)f
        for match in _NAMED_PLACEHOLDER_PATTERN.finditer(processed):
            name = match.group(1)
            format_type = match.group(2)
            placeholder_str = match.group(0)

            replacement = _get_placeholder_marker(format_type)
            self._placeholder_info.append(PlaceholderInfo(
                original=placeholder_str,
                name=name,
                format_type=format_type,
                positional=False,
            ))
            processed = processed.replace(placeholder_str, replacement, 1)

        # Find and replace positional placeholders: %s, %d, %f
        position = 0
        for match in _POSITIONAL_PLACEHOLDER_PATTERN.finditer(processed):
            format_type = match.group(1)
            placeholder_str = match.group(0)

            replacement = _get_placeholder_marker(format_type)
            self._placeholder_info.append(PlaceholderInfo(
                original=placeholder_str,
                name=str(position),
                format_type=format_type,
                positional=True,
            ))
            processed = processed.replace(placeholder_str, replacement, 1)
            position += 1

        return processed

    def _create_placeholder_refs(self, path: Path) -> List[PlaceholderReference]:
        """
        Walk the parsed AST and find placeholder markers.

        Args:
            path: Parsed JSONPath

        Returns:
            List of placeholder references
        """
        refs: List[PlaceholderReference] = []
        placeholder_index = 0

        def process_expression(expression: Any) -> None:
            nonlocal placeholder_index

            # Handle VariadicOperatorExpression (AND/OR) which has 'expressions' list
            if hasattr(expression, 'expressions'):
                for sub_expr in expression.expressions:
                    process_expression(sub_expr)
                return

            # Handle UnaryOperatorExpression (NOT) which has 'expression' in jsonpath2
            if hasattr(expression, 'expression') and not hasattr(expression, 'expressions'):
                inner = expression.expression
                if hasattr(inner, 'evaluate'):
                    process_expression(inner)
                return

            # Check for BinaryOperatorExpression with left_node_or_value/right_node_or_value
            if hasattr(expression, 'left_node_or_value') and hasattr(expression, 'right_node_or_value'):
                for attr in ('left_node_or_value', 'right_node_or_value'):
                    value = getattr(expression, attr)

                    if placeholder_index < len(self._placeholder_info):
                        ph = self._placeholder_info[placeholder_index]
                        if _is_placeholder_marker(value, ph.format_type):
                            refs.append(PlaceholderReference(
                                expression=expression,
                                attribute=attr,
                                name=ph.name,
                                format_type=ph.format_type,
                            ))
                            placeholder_index += 1

                # Recursively process sub-expressions
                if hasattr(expression.left_node_or_value, 'evaluate'):
                    process_expression(expression.left_node_or_value)
                if hasattr(expression.right_node_or_value, 'evaluate'):
                    process_expression(expression.right_node_or_value)

        def process_subscript(subscript: Any) -> None:
            if hasattr(subscript, 'expression'):
                process_expression(subscript.expression)

        # Traverse the node chain starting from root
        current_node = path.root_node
        while current_node:
            if hasattr(current_node, 'subscripts'):
                for subscript in current_node.subscripts:
                    process_subscript(subscript)
            current_node = getattr(current_node, 'next_node', None)

        return refs

    def _bind_placeholders(
        self,
        refs: List[PlaceholderReference],
        params: Union[Tuple[Any, ...], Dict[str, Any]],
    ) -> None:
        """
        Bind parameter values to all placeholders in AST.

        Args:
            refs: Placeholder references to bind
            params: Parameter values (tuple for positional, dict for named)

        Raises:
            MissingParameterError: If a required parameter is missing
        """
        for ref in refs:
            if ref.name.isdigit():
                # Positional parameter
                idx = int(ref.name)
                if not isinstance(params, (list, tuple)) or idx >= len(params):
                    raise MissingParameterError(
                        f"Missing positional parameter at index {idx}",
                        param_index=idx,
                    )
                value = params[idx]
            else:
                # Named parameter
                if not isinstance(params, dict) or ref.name not in params:
                    raise MissingParameterError(
                        f"Missing named parameter: {ref.name}",
                        param_name=ref.name,
                    )
                value = params[ref.name]

            ref.bind(value)

    def match(
        self, data: Any, params: Union[Tuple[Any, ...], Dict[str, Any]]
    ) -> Iterator[MatchData]:
        """
        Match data with bound parameters.

        Thread-safe: creates a deep copy of the AST for each execution.

        Args:
            data: Data to match
            params: Parameter values (tuple for positional, dict for named)

        Returns:
            Iterator of MatchData
        """
        # Create a deep copy of the AST for thread safety
        path_copy = copy.deepcopy(self._path)

        # Find placeholders in the copied AST
        refs = self._create_placeholder_refs(path_copy)

        # Bind parameter values
        self._bind_placeholders(refs, params)

        # Execute the path with bound parameters
        return path_copy.match(data)

    def find(
        self, data: Any, params: Union[Tuple[Any, ...], Dict[str, Any]]
    ) -> List[Any]:
        """
        Find all matching values.

        Args:
            data: Data to search
            params: Parameter values (tuple for positional, dict for named)

        Returns:
            List of matching values
        """
        return [match.current_value for match in self.match(data, params)]

    def find_one(
        self, data: Any, params: Union[Tuple[Any, ...], Dict[str, Any]]
    ) -> Optional[Any]:
        """
        Find first matching value.

        Args:
            data: Data to search
            params: Parameter values (tuple for positional, dict for named)

        Returns:
            First matching value or None
        """
        for match in self.match(data, params):
            return match.current_value
        return None

    def finditer(
        self, data: Any, params: Union[Tuple[Any, ...], Dict[str, Any]]
    ) -> Iterator[Any]:
        """
        Iterate over matching values.

        Args:
            data: Data to search
            params: Parameter values (tuple for positional, dict for named)

        Yields:
            Matching values
        """
        for match in self.match(data, params):
            yield match.current_value


@lru_cache(maxsize=128)
def parse(template: str) -> ParametrizedPath:
    """
    Parse JSONPath expression with C-style placeholders.

    Results are cached for better performance.

    Args:
        template: JSONPath with %s, %d, %f or %(name)s placeholders

    Returns:
        ParametrizedPath that can be executed with different parameter values

    Examples:
        >>> path = parse("$[?(@.age > %d)]")
        >>> results = path.match(data, (27,))
        >>>
        >>> path = parse("$[?(@.name = %(name)s)]")
        >>> results = path.match(data, {"name": "Alice"})
    """
    return ParametrizedPath(template)


def clear_cache() -> None:
    """Clear the parsed path cache."""
    parse.cache_clear()
