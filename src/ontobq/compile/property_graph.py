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

"""Compile Domain IR and mapping-view artifacts into property-graph DDL."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ontobq.compile.mapping_views import MappingViewArtifact
    from ontobq.ir import Domain, EntityDefinition, RelationshipDefinition

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BACKTICK = "`"
_TABLE_INDENT = "  "
_CLAUSE_INDENT = "    "
_REFS_INDENT = "      "


@dataclass(frozen=True)
class PropertyGraphArtifact:
    """Compiled ``CREATE OR REPLACE PROPERTY GRAPH`` statement.

    ``qualified_name`` is the unquoted ``project.dataset.graph`` target; ``sql``
    backtick-quotes it. ``dependencies`` lists emitted node then edge view
    qualified names in IR insertion order.
    """

    semantic_name: str
    graph_name: str
    qualified_name: str
    sql: str
    dependencies: tuple[str, ...]


def compile_property_graph(
    domain: Domain,
    mapping_view_artifacts: Sequence[MappingViewArtifact],
) -> PropertyGraphArtifact:
    """Return one property-graph artifact from IR plus mapping-view artifacts.

    Node and edge order follow IR insertion order. Identical IR and artifacts
    yield byte-for-byte identical SQL. Missing artifacts, a missing or dotted
    graph name, or duplicate or undeclared node keys raise ``ValueError``.
    """

    graph_name = _require_graph_name(domain.bigquery.graph)
    index = _artifact_index(mapping_view_artifacts)
    nodes = tuple(_render_node(name, entity, index) for name, entity in domain.entities.items())
    edges = tuple(
        _render_edge(domain, name, relationship, index)
        for name, relationship in domain.relationships.items()
    )
    return _graph_artifact(domain, graph_name, index, nodes, edges)


def _require_graph_name(graph_name: str) -> str:
    if not graph_name:
        raise ValueError("missing spec.bigquery.graph")
    if _SAFE_IDENTIFIER.fullmatch(graph_name) is None:
        raise ValueError(
            f"invalid spec.bigquery.graph {graph_name!r}: must be one BigQuery identifier component"
        )
    return graph_name


def _artifact_index(
    artifacts: Sequence[MappingViewArtifact],
) -> dict[tuple[str, str], MappingViewArtifact]:
    return {(item.kind, item.semantic_name): item for item in artifacts}


def _graph_artifact(
    domain: Domain,
    graph_name: str,
    index: Mapping[tuple[str, str], MappingViewArtifact],
    nodes: tuple[str, ...],
    edges: tuple[str, ...],
) -> PropertyGraphArtifact:
    qualified_name = _qualified_graph_name(domain)
    return PropertyGraphArtifact(
        semantic_name=domain.metadata.name,
        graph_name=graph_name,
        qualified_name=qualified_name,
        sql=_render_graph_sql(qualified_name, nodes, edges),
        dependencies=_dependency_names(domain, index),
    )


def _qualified_graph_name(domain: Domain) -> str:
    target = domain.bigquery
    return f"{target.project}.{target.dataset}.{target.graph}"


def _dependency_names(
    domain: Domain, index: Mapping[tuple[str, str], MappingViewArtifact]
) -> tuple[str, ...]:
    entities = tuple(
        _require_artifact(index, "entity", name).qualified_name for name in domain.entities
    )
    relationships = tuple(
        _require_artifact(index, "relationship", name).qualified_name
        for name in domain.relationships
    )
    return entities + relationships


def _render_graph_sql(qualified_name: str, nodes: tuple[str, ...], edges: tuple[str, ...]) -> str:
    parts = [
        "CREATE OR REPLACE PROPERTY GRAPH ",
        _quote_resource(qualified_name),
        "\nNODE TABLES (\n",
        ",\n".join(nodes),
        "\n)",
    ]
    if edges:
        parts.extend(["\nEDGE TABLES (\n", ",\n".join(edges), "\n)"])
    parts.append(";\n")
    return "".join(parts)


def _render_node(
    name: str,
    entity: EntityDefinition,
    index: Mapping[tuple[str, str], MappingViewArtifact],
) -> str:
    artifact = _require_artifact(index, "entity", name)
    key = _validated_node_key(name, entity, artifact)
    lines = (
        _TABLE_INDENT + _quote_resource(artifact.qualified_name),
        _CLAUSE_INDENT + _as_clause(name),
        _CLAUSE_INDENT + _paren_list("KEY", key),
        _CLAUSE_INDENT + _label_clause(name),
        _CLAUSE_INDENT + _paren_list("PROPERTIES", tuple(entity.properties)),
    )
    return "\n".join(lines)


def _validated_node_key(
    name: str,
    entity: EntityDefinition,
    artifact: MappingViewArtifact,
) -> tuple[str, ...]:
    key = entity.key
    _reject_duplicate_keys(name, key)
    _reject_undeclared_keys(name, key, entity, artifact)
    return key


def _reject_duplicate_keys(entity_name: str, key: tuple[str, ...]) -> None:
    seen: set[str] = set()
    for column in key:
        if column in seen:
            raise ValueError(f"duplicate key {column!r} on entity {entity_name!r}")
        seen.add(column)


def _reject_undeclared_keys(
    entity_name: str,
    key: tuple[str, ...],
    entity: EntityDefinition,
    artifact: MappingViewArtifact,
) -> None:
    allowed = set(entity.properties) | set(artifact.output_columns)
    for column in key:
        if column not in allowed:
            raise ValueError(f"undeclared key {column!r} on entity {entity_name!r}")


def _render_edge(
    domain: Domain,
    name: str,
    relationship: RelationshipDefinition,
    index: Mapping[tuple[str, str], MappingViewArtifact],
) -> str:
    artifact = _require_artifact(index, "relationship", name)
    lines = [
        _TABLE_INDENT + _quote_resource(artifact.qualified_name),
        _CLAUSE_INDENT + _as_clause(name),
        _CLAUSE_INDENT + _paren_list("KEY", artifact.edge_key_columns),
        *_endpoint_lines("SOURCE KEY", artifact.from_columns, relationship.from_entity, domain),
        *_endpoint_lines("DESTINATION KEY", artifact.to_columns, relationship.to_entity, domain),
        _CLAUSE_INDENT + _label_clause(name),
    ]
    property_names = tuple(relationship.properties)
    if property_names:
        lines.append(_CLAUSE_INDENT + _paren_list("PROPERTIES", property_names))
    return "\n".join(lines)


def _endpoint_lines(
    keyword: str,
    helper_columns: tuple[str, ...],
    entity_name: str,
    domain: Domain,
) -> tuple[str, str]:
    return (
        _CLAUSE_INDENT + _paren_list(keyword, helper_columns),
        _REFS_INDENT + _references_clause(entity_name, _entity_key(domain, entity_name)),
    )


def _entity_key(domain: Domain, name: str) -> tuple[str, ...]:
    entity = domain.entities.get(name)
    if entity is None:
        raise ValueError(f"unknown entity {name!r}")
    return entity.key


def _require_artifact(
    index: Mapping[tuple[str, str], MappingViewArtifact],
    kind: Literal["entity", "relationship"],
    name: str,
) -> MappingViewArtifact:
    artifact = index.get((kind, name))
    if artifact is None:
        raise ValueError(f"missing {kind} mapping-view artifact for {name!r}")
    return artifact


def _as_clause(name: str) -> str:
    return "".join(("AS ", _quote_identifier(name)))


def _label_clause(name: str) -> str:
    return "".join(("LABEL ", _quote_identifier(name)))


def _paren_list(keyword: str, names: tuple[str, ...]) -> str:
    return "".join((keyword, " (", _join_identifiers(names), ")"))


def _references_clause(entity_name: str, key_names: tuple[str, ...]) -> str:
    return "".join(
        (
            "REFERENCES ",
            _quote_identifier(entity_name),
            " (",
            _join_identifiers(key_names),
            ")",
        )
    )


def _join_identifiers(names: tuple[str, ...]) -> str:
    return ", ".join(_quote_identifier(name) for name in names)


def _quote_identifier(identifier: str) -> str:
    if _SAFE_IDENTIFIER.fullmatch(identifier) is not None:
        return identifier
    return _quote_resource(identifier)


def _quote_resource(name: str) -> str:
    escaped = name.replace(_BACKTICK, _BACKTICK * 2)
    return f"{_BACKTICK}{escaped}{_BACKTICK}"
