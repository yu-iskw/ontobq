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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NamedTuple

from ontobq.naming import (
    edge_key_column,
    edge_view_name,
    from_key_column,
    node_view_name,
    to_key_column,
)
from ontobq.sql.interpolate import quote_resource, select_item

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from ontobq.ir import (
        Domain,
        EntityDefinition,
        MappingValue,
        RelationshipDefinition,
    )


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


def _reject_duplicate_qualified_names(artifacts: tuple[MappingViewArtifact, ...]) -> None:
    """Raise when two semantic objects normalize to the same view target."""

    seen: dict[str, str] = {}
    for artifact in artifacts:
        previous = seen.setdefault(artifact.qualified_name, artifact.semantic_name)
        if previous != artifact.semantic_name:
            raise ValueError(
                "duplicate mapping view target "
                f"{artifact.qualified_name!r} for {previous!r} and {artifact.semantic_name!r}"
            )


def _qualified_name(domain: Domain, view_name: str) -> str:
    target = domain.bigquery
    return f"{target.project}.{target.dataset}.{view_name}"


def _create_view_sql(
    qualified_name: str, projection: tuple[_AliasedSelect, ...], source: str
) -> str:
    body = ",\n".join("  " + item.sql for item in projection)
    return "".join(
        (
            "CREATE OR REPLACE VIEW ",
            quote_resource(qualified_name),
            " AS\nSELECT\n",
            body,
            "\nFROM ",
            quote_resource(source),
            ";\n",
        )
    )


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


def _select_for_alias(value: MappingValue, alias: str) -> _AliasedSelect:
    return _AliasedSelect(select_item(value, alias), alias)


def _lookup(values: Mapping[str, MappingValue], name: str, where: str) -> MappingValue:
    value = values.get(name)
    if value is None:
        raise ValueError(f"missing {where} mapping for {name!r}")
    return value


def _property_projection(
    declared: Mapping[str, object],
    mapped: Mapping[str, MappingValue],
    where: str,
) -> tuple[_AliasedSelect, ...]:
    return tuple(_select_for_alias(_lookup(mapped, name, where), name) for name in declared)


def _compile_entity(domain: Domain, name: str, entity: EntityDefinition) -> MappingViewArtifact:
    view_name = node_view_name(domain.metadata.name, name)
    projection = _property_projection(
        entity.properties, entity.mapping.properties, "entity property"
    )
    return _entity_artifact(domain, name, view_name, entity.mapping.source, projection)


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


def _require_entity(domain: Domain, name: str) -> EntityDefinition:
    entity = domain.entities.get(name)
    if entity is None:
        raise ValueError(f"unknown entity {name!r}")
    return entity


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


def _compile_relationship(
    domain: Domain, name: str, relationship: RelationshipDefinition
) -> MappingViewArtifact:
    view_name = edge_view_name(domain.metadata.name, name)
    projection = _relationship_projection(domain, relationship)
    return _relationship_artifact(domain, name, view_name, relationship.mapping.source, projection)


def compile_mapping_views(domain: Domain) -> tuple[MappingViewArtifact, ...]:
    """Return mapping-view artifacts in IR insertion order.

    Entity views come first, then relationship views. Identical IR yields
    byte-for-byte identical SQL. Invalid IR raises ``ValueError``.
    """

    artifacts = tuple(
        _compile_entity(domain, name, entity) for name, entity in domain.entities.items()
    ) + tuple(
        _compile_relationship(domain, name, relationship)
        for name, relationship in domain.relationships.items()
    )
    _reject_duplicate_qualified_names(artifacts)
    return artifacts
