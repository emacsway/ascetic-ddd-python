"""
Extension for jsonpath-rfc9535 parser to support parameterized expressions.

Extends the parser to recognize placeholders (%s, %d, %f, %(name)s)
and bind values at execution time.
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union
import re

from jsonpath_rfc9535 import JSONPathEnvironment


# Unique placeholder markers (chosen to avoid collision with real data)
PLACEHOLDER_MARKER_INT = -8765432109876
PLACEHOLDER_MARKER_FLOAT = -8765432109876.5
PLACEHOLDER_MARKER_STR = "__JSONPATH_PARAM_PLACEHOLDER_x9y8z7__"

# Pre-compiled regex patterns for better performance
_NAMED_PLACEHOLDER_PATTERN = re.compile(r'%\((\w+)\)([sdf])')
_POSITIONAL_PLACEHOLDER_PATTERN = re.compile(r'%([sdf])')


class JSONPathParameterError(Exception):
    """Base exception for JSONPath parameter binding errors."""
    pass


class MissingParameterError(JSONPathParameterError):
    """Raised when a required parameter is missing."""

    def __init__(self, message: str, param_name: str = None, param_index: int = None):
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


def _get_placeholder_marker(format_type: str) -> str:
    """
    Get the appropriate placeholder marker for a format type.

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


def _get_marker_for_replacement(format_type: str) -> str:
    """
    Get the marker string to search for during replacement.

    Args:
        format_type: 's', 'd', or 'f'

    Returns:
        The marker string as it appears in the processed template
    """
    if format_type == 's':
        return f'"{PLACEHOLDER_MARKER_STR}"'
    elif format_type == 'd':
        return str(PLACEHOLDER_MARKER_INT)
    elif format_type == 'f':
        return str(PLACEHOLDER_MARKER_FLOAT)
    else:
        raise ValueError(f"Unknown format type: {format_type}")


def _format_value(value: Any, format_type: str) -> str:
    """
    Format a value for insertion into JSONPath expression.

    Args:
        value: The value to format
        format_type: 's', 'd', or 'f'

    Returns:
        Formatted string representation
    """
    if format_type == 's':
        if isinstance(value, bool):
            return 'true' if value else 'false'
        escaped_value = str(value).replace('"', '\\"')
        return f'"{escaped_value}"'
    elif format_type == 'd':
        return str(int(value))
    elif format_type == 'f':
        return str(float(value))
    else:
        raise ValueError(f"Unknown format type: {format_type}")


class ParametrizedExpression:
    """
    JSONPath expression with placeholder support (RFC 9535 compliant).

    Parses template once, binds different values at execution time.
    Thread-safe: uses LRU cache for compiled queries.
    """

    def __init__(self, template: str, env: Optional[JSONPathEnvironment] = None):
        """
        Parse template with placeholders.

        Args:
            template: JSONPath with %s, %d, %f or %(name)s placeholders
            env: JSONPath environment (optional, creates default if not provided)
        """
        self.template = template
        self.env = env or JSONPathEnvironment()
        self._placeholder_info: List[PlaceholderInfo] = []

        # Parse template and replace placeholders with markers
        self._processed_template = self._preprocess_template(template)

    @property
    def placeholders(self) -> List[PlaceholderInfo]:
        """Return placeholder info for compatibility."""
        return self._placeholder_info

    def _preprocess_template(self, template: str) -> str:
        """
        Replace placeholders with temporary markers.

        Args:
            template: Original template with placeholders

        Returns:
            Processed template with markers
        """
        processed = template

        # Find and replace named placeholders: %(name)s, %(age)d, %(price)f
        for match in _NAMED_PLACEHOLDER_PATTERN.finditer(template):
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

    def _build_bound_expression(
        self, params: Union[Tuple[Any, ...], Dict[str, Any]]
    ) -> str:
        """
        Build JSONPath expression with bound parameter values.

        Args:
            params: Parameter values (tuple for positional, dict for named)

        Returns:
            JSONPath expression string with values substituted

        Raises:
            MissingParameterError: If a required parameter is missing
        """
        result = self._processed_template

        for ph_info in self._placeholder_info:
            # Get the value for this placeholder
            if ph_info.positional:
                idx = int(ph_info.name)
                if not isinstance(params, (list, tuple)) or idx >= len(params):
                    raise MissingParameterError(
                        f"Missing positional parameter at index {idx}",
                        param_index=idx,
                    )
                value = params[idx]
            else:
                if not isinstance(params, dict) or ph_info.name not in params:
                    raise MissingParameterError(
                        f"Missing named parameter: {ph_info.name}",
                        param_name=ph_info.name,
                    )
                value = params[ph_info.name]

            # Replace the marker with the formatted value
            marker = _get_marker_for_replacement(ph_info.format_type)
            replacement = _format_value(value, ph_info.format_type)
            result = result.replace(marker, replacement, 1)

        return result

    @lru_cache(maxsize=128)
    def _compile_expression(self, expression: str):
        """
        Compile a JSONPath expression with caching.

        Args:
            expression: JSONPath expression string

        Returns:
            Compiled JSONPath query
        """
        return self.env.compile(expression)

    def _get_compiled_query(self, params: Union[Tuple[Any, ...], Dict[str, Any]]):
        """
        Get compiled query for the given parameters.

        Args:
            params: Parameter values

        Returns:
            Compiled JSONPath query
        """
        bound_expression = self._build_bound_expression(params)
        return self._compile_expression(bound_expression)

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
        query = self._get_compiled_query(params)
        result = query.find(data)
        return result.values()

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
        query = self._get_compiled_query(params)
        node = query.find_one(data)
        return node.value if node else None

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
        query = self._get_compiled_query(params)
        for node in query.finditer(data):
            yield node.value

    def clear_cache(self) -> None:
        """Clear the compiled expression cache."""
        self._compile_expression.cache_clear()


def parse(
    template: str, env: Optional[JSONPathEnvironment] = None
) -> ParametrizedExpression:
    """
    Parse JSONPath expression with C-style placeholders.

    Args:
        template: JSONPath with %s, %d, %f or %(name)s placeholders
        env: JSONPath environment (optional)

    Returns:
        ParametrizedExpression that can be executed with different parameter values

    Examples:
        >>> expr = parse("$[?@.age > %d]")
        >>> result = expr.find(data, (27,))
        >>>
        >>> expr = parse("$[?@.name == %(name)s]")
        >>> result = expr.find(data, {"name": "Alice"})
    """
    return ParametrizedExpression(template, env)
