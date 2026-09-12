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

"""Compile Domain IR into deterministic mapping-view CREATE OR REPLACE VIEW DDL."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NamedTuple

from ontobq.ir import ColumnMapping, ExpressionMapping
from ontobq.naming import (
    edge_key_column,
    edge_view_name,
    from_key_column,
    node_view_name,
    to_key_column,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from ontobq.ir import (
        Domain,
        EntityDefinition,
        MappingValue,
        RelationshipDefinition,
    )

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_QUOTES = "'\"`"
_BACKTICK = "`"


class _AliasedSelect(NamedTuple):
    """One SELECT item and the output column alias it produces."""

    sql: str
    alias: str


class _RelationshipProjection(NamedTuple):
    """SELECT list plus helper-column groups for one relationship view."""

    items: tuple[_AliasedSelect, ...]
    edge_key_columns: tuple[str, ...]
    from_columns: tuple[str, ...]
    to_columns: tuple[str, ...]


@dataclass(frozen=True)
class MappingViewArtifact:
    """Compiled mapping view for one entity or relationship.

    ``kind`` is ``"entity"`` or ``"relationship"``. Helper-column tuples are
    empty on entity views. ``qualified_name`` is the unquoted
    ``project.dataset.view`` target; ``sql`` backtick-quotes it.
    """

    kind: Literal["entity", "relationship"]
    semantic_name: str
    view_name: str
    qualified_name: str
    sql: str
    source: str
    output_columns: tuple[str, ...]
    edge_key_columns: tuple[str, ...] = ()
    from_columns: tuple[str, ...] = ()
    to_columns: tuple[str, ...] = ()


def compile_mapping_views(domain: Domain) -> tuple[MappingViewArtifact, ...]:
    """Return mapping-view artifacts in IR insertion order.

    Entity views come first, then relationship views. Identical IR yields
    byte-for-byte identical SQL. Invalid IR raises ``ValueError``.
    """

    entities = tuple(
        _compile_entity(domain, name, entity) for name, entity in domain.entities.items()
    )
    relationships = tuple(
        _compile_relationship(domain, name, relationship)
        for name, relationship in domain.relationships.items()
    )
    return entities + relationships


def _compile_entity(domain: Domain, name: str, entity: EntityDefinition) -> MappingViewArtifact:
    view_name = node_view_name(domain.metadata.name, name)
    projection = _property_projection(
        entity.properties, entity.mapping.properties, "entity property"
    )
    return _entity_artifact(domain, name, view_name, entity.mapping.source, projection)


def _entity_artifact(
    domain: Domain,
    name: str,
    view_name: str,
    source: str,
    projection: tuple[_AliasedSelect, ...],
) -> MappingViewArtifact:
    qualified_name = _qualified_name(domain, view_name)
    return MappingViewArtifact(
        kind="entity",
        semantic_name=name,
        view_name=view_name,
        qualified_name=qualified_name,
        sql=_create_view_sql(qualified_name, projection, source),
        source=source,
        output_columns=tuple(item.alias for item in projection),
    )


def _compile_relationship(
    domain: Domain, name: str, relationship: RelationshipDefinition
) -> MappingViewArtifact:
    view_name = edge_view_name(domain.metadata.name, name)
    projection = _relationship_projection(domain, relationship)
    return _relationship_artifact(domain, name, view_name, relationship.mapping.source, projection)


def _relationship_artifact(
    domain: Domain,
    name: str,
    view_name: str,
    source: str,
    projection: _RelationshipProjection,
) -> MappingViewArtifact:
    qualified_name = _qualified_name(domain, view_name)
    return MappingViewArtifact(
        kind="relationship",
        semantic_name=name,
        view_name=view_name,
        qualified_name=qualified_name,
        sql=_create_view_sql(qualified_name, projection.items, source),
        source=source,
        output_columns=tuple(item.alias for item in projection.items),
        edge_key_columns=projection.edge_key_columns,
        from_columns=projection.from_columns,
        to_columns=projection.to_columns,
    )


def _relationship_projection(
    domain: Domain, relationship: RelationshipDefinition
) -> _RelationshipProjection:
    mapping = relationship.mapping
    edge = _edge_key_projection(mapping.key)
    source = _endpoint_projection(
        mapping.from_endpoint,
        _require_entity(domain, relationship.from_entity).key,
        from_key_column,
        "from-endpoint",
    )
    dest = _endpoint_projection(
        mapping.to_endpoint,
        _require_entity(domain, relationship.to_entity).key,
        to_key_column,
        "to-endpoint",
    )
    props = _property_projection(
        relationship.properties, mapping.properties, "relationship property"
    )
    return _RelationshipProjection(
        edge + source + dest + props,
        _aliases(edge),
        _aliases(source),
        _aliases(dest),
    )


def _aliases(items: tuple[_AliasedSelect, ...]) -> tuple[str, ...]:
    return tuple(item.alias for item in items)


def _edge_key_projection(keys: tuple[MappingValue, ...]) -> tuple[_AliasedSelect, ...]:
    return tuple(
        _select_for_alias(value, edge_key_column(ordinal)) for ordinal, value in enumerate(keys)
    )


def _endpoint_projection(
    values: Mapping[str, MappingValue],
    key_names: tuple[str, ...],
    namer: Callable[[str], str],
    where: str,
) -> tuple[_AliasedSelect, ...]:
    return tuple(_select_for_alias(_lookup(values, name, where), namer(name)) for name in key_names)


def _property_projection(
    declared: Mapping[str, object],
    mapped: Mapping[str, MappingValue],
    where: str,
) -> tuple[_AliasedSelect, ...]:
    return tuple(_select_for_alias(_lookup(mapped, name, where), name) for name in declared)


def _select_for_alias(value: MappingValue, alias: str) -> _AliasedSelect:
    sql = f"{_render_mapped_value(value)} AS {_quote_identifier(alias)}"
    return _AliasedSelect(sql, alias)


def _lookup(values: Mapping[str, MappingValue], name: str, where: str) -> MappingValue:
    value = values.get(name)
    if value is None:
        raise ValueError(f"missing {where} mapping for {name!r}")
    return value


def _require_entity(domain: Domain, name: str) -> EntityDefinition:
    entity = domain.entities.get(name)
    if entity is None:
        raise ValueError(f"unknown entity {name!r}")
    return entity


def _qualified_name(domain: Domain, view_name: str) -> str:
    target = domain.bigquery
    return f"{target.project}.{target.dataset}.{view_name}"


def _create_view_sql(
    qualified_name: str, projection: tuple[_AliasedSelect, ...], source: str
) -> str:
    body = ",\n".join(f"  {item.sql}" for item in projection)
    view = _quote_resource(qualified_name)
    from_clause = _quote_resource(source)
    return f"CREATE OR REPLACE VIEW {view} AS\nSELECT\n{body}\nFROM {from_clause};\n"


def _render_mapped_value(value: MappingValue) -> str:
    if isinstance(value, ColumnMapping):
        return _quote_identifier(value.column)
    if isinstance(value, ExpressionMapping):
        return _render_expression(value.expression)
    raise TypeError(f"unsupported mapping value type: {type(value)!r}")


def _render_expression(expression: str) -> str:
    if _needs_parentheses(expression):
        return f"({expression})"
    return expression


def _needs_parentheses(expression: str) -> bool:
    """True when a top-level comma or AS would make ``AS alias`` ambiguous."""

    depth = 0
    index = 0
    while index < len(expression):
        index, depth, found = _advance_expression(expression, index, depth)
        if found:
            return True
    return False


def _advance_expression(expression: str, index: int, depth: int) -> tuple[int, int, bool]:
    char = expression[index]
    if char in _QUOTES:
        return _skip_quoted(expression, index), depth, False
    if char in "()":
        return index + 1, _next_paren_depth(char, depth), False
    ambiguous = depth == 0 and (char == "," or _is_as_keyword_at(expression, index))
    return index + 1, depth, ambiguous


def _next_paren_depth(char: str, depth: int) -> int:
    if char == "(":
        return depth + 1
    if depth == 0:
        return 0
    return depth - 1


def _skip_quoted(text: str, start: int) -> int:
    quote = text[start]
    index = start + 1
    while index < len(text):
        index, done = _step_quoted(text, index, quote)
        if done:
            return index
    return len(text)


def _step_quoted(text: str, index: int, quote: str) -> tuple[int, bool]:
    char = text[index]
    escaped = char == "\\" and quote != "`"
    doubled = char == quote and index + 1 < len(text) and text[index + 1] == quote
    if escaped or doubled:
        return index + 2, False
    return index + 1, char == quote


def _is_as_keyword_at(text: str, index: int) -> bool:
    if text[index : index + 2].upper() != "AS":
        return False
    before_ok = index == 0 or not _is_identifier_char(text[index - 1])
    after_ok = index + 2 >= len(text) or not _is_identifier_char(text[index + 2])
    return before_ok and after_ok


def _is_identifier_char(char: str) -> bool:
    return char.isalnum() or char == "_"


def _quote_identifier(identifier: str) -> str:
    if _SAFE_IDENTIFIER.fullmatch(identifier) is not None:
        return identifier
    return _quote_resource(identifier)


def _quote_resource(name: str) -> str:
    escaped = name.replace(_BACKTICK, _BACKTICK * 2)
    return f"{_BACKTICK}{escaped}{_BACKTICK}"
