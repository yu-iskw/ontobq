# Copyright 2025 yu-iskw
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Render trusted Domain mapping values as GoogleSQL fragments.

This module is the shared interpolator for mapping-view DDL and integrity
SELECTs. It is not the mapping-view compiler: callers must not import
``compile_mapping_views`` to reuse quoting.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ontobq.ir import ColumnMapping, ExpressionMapping

if TYPE_CHECKING:
    from ontobq.ir import MappingValue

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_QUOTES = "'\"`"
_BACKTICK = "`"
# GoogleSQL reserved keywords (https://github.com/google/googlesql lexical.md).
_RESERVED_KEYWORDS = frozenset(
    [
        "ALL",
        "AND",
        "ANY",
        "ARRAY",
        "AS",
        "ASC",
        "ASSERT_ROWS_MODIFIED",
        "AT",
        "BETWEEN",
        "BY",
        "CASE",
        "CAST",
        "COLLATE",
        "CONTAINS",
        "CREATE",
        "CROSS",
        "CUBE",
        "CURRENT",
        "DEFAULT",
        "DEFINE",
        "DESC",
        "DISTINCT",
        "ELSE",
        "END",
        "ENUM",
        "ESCAPE",
        "EXCEPT",
        "EXCLUDE",
        "EXISTS",
        "EXTRACT",
        "FALSE",
        "FETCH",
        "FOLLOWING",
        "FOR",
        "FROM",
        "FULL",
        "GRAPH_TABLE",
        "GROUP",
        "GROUPING",
        "GROUPS",
        "HASH",
        "HAVING",
        "IF",
        "IGNORE",
        "IN",
        "INNER",
        "INTERSECT",
        "INTERVAL",
        "INTO",
        "IS",
        "JOIN",
        "LATERAL",
        "LEFT",
        "LIKE",
        "LIMIT",
        "LOOKUP",
        "MERGE",
        "NATURAL",
        "NEW",
        "NO",
        "NOT",
        "NULL",
        "NULLS",
        "OF",
        "ON",
        "OR",
        "ORDER",
        "OUTER",
        "OVER",
        "PARTITION",
        "PRECEDING",
        "PROTO",
        "QUALIFY",
        "RANGE",
        "RECURSIVE",
        "RESPECT",
        "RIGHT",
        "ROLLUP",
        "ROWS",
        "SELECT",
        "SET",
        "SOME",
        "STRUCT",
        "TABLESAMPLE",
        "THEN",
        "TO",
        "TREAT",
        "TRUE",
        "UNBOUNDED",
        "UNION",
        "UNNEST",
        "USING",
        "WHEN",
        "WHERE",
        "WINDOW",
        "WITH",
        "WITHIN",
    ]
)


def quote_resource(name: str) -> str:
    """Wrap a BigQuery resource name in one backtick pair."""

    escaped = name.replace(_BACKTICK, _BACKTICK * 2)
    return f"{_BACKTICK}{escaped}{_BACKTICK}"


def quote_identifier(identifier: str) -> str:
    """Return ``identifier`` unquoted when it is a safe, non-reserved name."""

    safe = _SAFE_IDENTIFIER.fullmatch(identifier) is not None
    if safe and identifier.upper() not in _RESERVED_KEYWORDS:
        return identifier
    return quote_resource(identifier)


def _is_line_comment_at(text: str, index: int) -> bool:
    return text.startswith("--", index)


def _is_block_comment_at(text: str, index: int) -> bool:
    return text.startswith("/*", index)


def _skip_block_comment(text: str, start: int) -> int:
    end = text.find("*/", start + 2)
    if end == -1:
        raise ValueError("unterminated block comment in expression mapping")
    return end + 2


def _skip_line_comment(text: str, start: int) -> int:
    newline = text.find("\n", start)
    if newline == -1:
        return len(text)
    return newline + 1


def _step_quoted(text: str, index: int, quote: str) -> tuple[int, bool]:
    char = text[index]
    escaped = char == "\\" and quote != "`"
    doubled = char == quote and index + 1 < len(text) and text[index + 1] == quote
    if escaped or doubled:
        return index + 2, False
    return index + 1, char == quote


def _skip_quoted(text: str, start: int) -> int:
    quote = text[start]
    index = start + 1
    while index < len(text):
        index, done = _step_quoted(text, index, quote)
        if done:
            return index
    return len(text)


def _skip_comment(expression: str, index: int) -> int | None:
    if _is_line_comment_at(expression, index):
        return _skip_line_comment(expression, index)
    if not _is_block_comment_at(expression, index):
        return None
    return _skip_block_comment(expression, index)


def _skip_token(expression: str, index: int) -> int | None:
    if expression[index] in _QUOTES:
        return _skip_quoted(expression, index)
    return _skip_comment(expression, index)


def _next_paren_depth(char: str, depth: int) -> int:
    if char == "(":
        return depth + 1
    if depth == 0:
        return 0
    return depth - 1


def _is_identifier_char(char: str) -> bool:
    return char.isalnum() or char == "_"


def _is_as_keyword_at(text: str, index: int) -> bool:
    if text[index : index + 2].upper() != "AS":
        return False
    before_ok = index == 0 or not _is_identifier_char(text[index - 1])
    after_ok = index + 2 >= len(text) or not _is_identifier_char(text[index + 2])
    return before_ok and after_ok


def _advance_expression(expression: str, index: int, depth: int) -> tuple[int, int, bool]:
    skipped = _skip_token(expression, index)
    if skipped is not None:
        return skipped, depth, False
    if expression[index] in "()":
        return index + 1, _next_paren_depth(expression[index], depth), False
    ambiguous = depth == 0 and (expression[index] == "," or _is_as_keyword_at(expression, index))
    return index + 1, depth, ambiguous


def _has_top_level_comma_or_as(expression: str) -> bool:
    """True when a top-level comma or AS means the mapping is not a scalar."""

    depth = 0
    index = 0
    while index < len(expression):
        index, depth, found = _advance_expression(expression, index, depth)
        if found:
            return True
    return False


def _render_expression(expression: str) -> str:
    if _has_top_level_comma_or_as(expression):
        raise ValueError("expression mappings must be scalar GoogleSQL expressions")
    return expression


def render_mapping_value(value: MappingValue) -> str:
    """Render a column reference or a verbatim scalar expression."""

    if isinstance(value, ColumnMapping):
        return quote_identifier(value.column)
    if isinstance(value, ExpressionMapping):
        return _render_expression(value.expression)
    raise TypeError(f"unsupported mapping value type: {type(value)!r}")


def _consume_comment_scan(expression: str, index: int) -> tuple[int, bool]:
    skipped = _skip_token(expression, index)
    if skipped is None:
        return index + 1, False
    unclosed = _is_line_comment_at(expression, index) and "\n" not in expression[index:]
    return skipped, unclosed


def _ends_in_line_comment(expression: str) -> bool:
    index = 0
    while index < len(expression):
        index, ended = _consume_comment_scan(expression, index)
        if ended:
            return True
    return False


def _mapped_value_ends_in_line_comment(value: MappingValue) -> bool:
    return isinstance(value, ExpressionMapping) and _ends_in_line_comment(value.expression)


def _alias_clause(value: MappingValue, alias: str) -> str:
    quoted = quote_identifier(alias)
    if _mapped_value_ends_in_line_comment(value):
        return f"\n  AS {quoted}"
    return f" AS {quoted}"


def select_item(value: MappingValue, alias: str) -> str:
    """Return ``{rendered} AS {alias}``, breaking before ``AS`` after ``--``."""

    return render_mapping_value(value) + _alias_clause(value, alias)


def select_wrapped_item(function: str, value: MappingValue, alias: str) -> str:
    """Return ``FUNCTION({rendered}) AS {alias}`` for groupable evidence."""

    if _SAFE_IDENTIFIER.fullmatch(function) is None:
        raise ValueError(f"invalid SQL function name {function!r}")
    rendered = render_mapping_value(value)
    if _mapped_value_ends_in_line_comment(value):
        return f"{function}({rendered}\n){_alias_clause(value, alias)}"
    return f"{function}({rendered}){_alias_clause(value, alias)}"
