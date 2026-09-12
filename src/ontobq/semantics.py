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

"""Pure offline semantic checks OBQ001-OBQ008 over typed Domain IR."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ontobq.diagnostics import Diagnostic, Severity
from ontobq.naming import (
    edge_key_column,
    edge_view_name,
    from_key_column,
    node_view_name,
    to_key_column,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ontobq.ir import Domain, EntityDefinition, RelationshipDefinition

_RESERVED_PREFIXES = ("_ontobq_", "__ontobq_")


def _sort_key(diagnostic: Diagnostic) -> tuple[str, str, str, tuple[str, ...]]:
    return (diagnostic.code, diagnostic.path, diagnostic.message, diagnostic.evidence)


def _error(code: str, path: str, message: str, evidence: tuple[str, ...] = ()) -> Diagnostic:
    return Diagnostic(
        code=code, severity=Severity.ERROR, path=path, message=message, evidence=evidence
    )


def _optional(diagnostic: Diagnostic | None) -> tuple[Diagnostic, ...]:
    if diagnostic is None:
        return ()
    return (diagnostic,)


def _unknown_key_properties(name: str, entity: EntityDefinition) -> tuple[Diagnostic, ...]:
    declared = set(entity.properties)
    path = f"spec.entities.{name}.key"
    return tuple(
        _error("OBQ001", path, "entity key references unknown property", (key,))
        for key in entity.key
        if key not in declared
    )


def _entity_key_diagnostics(domain: Domain) -> tuple[Diagnostic, ...]:
    return tuple(
        item
        for name, entity in domain.entities.items()
        for item in _unknown_key_properties(name, entity)
    )


def _set_mismatch(
    code: str,
    path: str,
    declared: Iterable[str],
    mapped: Iterable[str],
    message: str,
) -> Diagnostic | None:
    evidence = tuple(sorted(set(declared) ^ set(mapped)))
    if not evidence:
        return None
    return _error(code, path, message, evidence)


def _entity_property_set_diagnostics(domain: Domain) -> tuple[Diagnostic, ...]:
    return tuple(
        item
        for name, entity in domain.entities.items()
        for item in _optional(
            _set_mismatch(
                "OBQ002",
                f"spec.entities.{name}.mapping.bigquery.properties",
                entity.properties,
                entity.mapping.properties,
                "entity property declaration/mapping sets differ",
            )
        )
    )


def _relationship_property_set_diagnostics(domain: Domain) -> tuple[Diagnostic, ...]:
    return tuple(
        item
        for name, rel in domain.relationships.items()
        for item in _optional(
            _set_mismatch(
                "OBQ006",
                f"spec.relationships.{name}.mapping.bigquery.properties",
                rel.properties,
                rel.mapping.properties,
                "relationship property declaration/mapping sets differ",
            )
        )
    )


def _missing_entity(
    domain: Domain,
    entity_name: str,
    code: str,
    path: str,
    message: str,
) -> tuple[Diagnostic, ...]:
    if entity_name in domain.entities:
        return ()
    return (_error(code, path, message, (entity_name,)),)


def _missing_relationship_entities(
    domain: Domain, name: str, rel: RelationshipDefinition
) -> tuple[Diagnostic, ...]:
    missing_from = _missing_entity(
        domain,
        rel.from_entity,
        "OBQ003",
        f"spec.relationships.{name}.from",
        "relationship source entity does not exist",
    )
    missing_to = _missing_entity(
        domain,
        rel.to_entity,
        "OBQ004",
        f"spec.relationships.{name}.to",
        "relationship destination entity does not exist",
    )
    return missing_from + missing_to


def _relationship_entity_diagnostics(domain: Domain) -> tuple[Diagnostic, ...]:
    return tuple(
        item
        for name, rel in domain.relationships.items()
        for item in _missing_relationship_entities(domain, name, rel)
    )


def _endpoint_mismatch(
    entity: EntityDefinition | None,
    rel_name: str,
    endpoint: Iterable[str],
    side: str,
) -> tuple[Diagnostic, ...]:
    if entity is None:
        return ()
    evidence = tuple(sorted(set(endpoint) ^ set(entity.key)))
    if not evidence:
        return ()
    path = f"spec.relationships.{rel_name}.mapping.bigquery.{side}"
    return (
        _error(
            "OBQ005",
            path,
            "endpoint mapping keys do not exactly equal referenced entity keys",
            evidence,
        ),
    )


def _endpoint_key_mismatches(
    domain: Domain, name: str, rel: RelationshipDefinition
) -> tuple[Diagnostic, ...]:
    from_diag = _endpoint_mismatch(
        domain.entities.get(rel.from_entity), name, rel.mapping.from_endpoint, "from"
    )
    to_diag = _endpoint_mismatch(
        domain.entities.get(rel.to_entity), name, rel.mapping.to_endpoint, "to"
    )
    return from_diag + to_diag


def _endpoint_key_diagnostics(domain: Domain) -> tuple[Diagnostic, ...]:
    return tuple(
        item
        for name, rel in domain.relationships.items()
        for item in _endpoint_key_mismatches(domain, name, rel)
    )


def _is_reserved(name: str) -> bool:
    return name.startswith(_RESERVED_PREFIXES)


def _one_entity_identifiers(name: str, entity: EntityDefinition) -> tuple[tuple[str, str], ...]:
    prefix = f"spec.entities.{name}"
    named = ((prefix, name),)
    keys = tuple((f"{prefix}.key", key) for key in entity.key)
    props = tuple((f"{prefix}.properties.{prop}", prop) for prop in entity.properties)
    return named + keys + props


def _entity_identifiers(domain: Domain) -> tuple[tuple[str, str], ...]:
    return tuple(
        item
        for name, entity in domain.entities.items()
        for item in _one_entity_identifiers(name, entity)
    )


def _one_relationship_identifiers(
    name: str, rel: RelationshipDefinition
) -> tuple[tuple[str, str], ...]:
    prefix = f"spec.relationships.{name}"
    mapping = f"{prefix}.mapping.bigquery"
    named = ((prefix, name),)
    props = tuple((f"{prefix}.properties.{prop}", prop) for prop in rel.properties)
    sources = tuple((f"{mapping}.from", key) for key in rel.mapping.from_endpoint)
    dests = tuple((f"{mapping}.to", key) for key in rel.mapping.to_endpoint)
    return named + props + sources + dests


def _relationship_identifiers(domain: Domain) -> tuple[tuple[str, str], ...]:
    return tuple(
        item
        for name, rel in domain.relationships.items()
        for item in _one_relationship_identifiers(name, rel)
    )


def _semantic_identifiers(domain: Domain) -> tuple[tuple[str, str], ...]:
    return (
        ("metadata.name", domain.metadata.name),
        ("spec.bigquery.graph", domain.bigquery.graph),
        *_entity_identifiers(domain),
        *_relationship_identifiers(domain),
    )


def _reserved_name_diagnostics(domain: Domain) -> tuple[Diagnostic, ...]:
    return tuple(
        _error("OBQ007", path, "compiler-reserved name used", (name,))
        for path, name in _semantic_identifiers(domain)
        if _is_reserved(name)
    )


def _multi_occupants(
    pairs: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    grouped: dict[str, list[str]] = {}
    for key, value in pairs:
        grouped.setdefault(key, []).append(value)
    return tuple((key, tuple(values)) for key, values in grouped.items() if len(values) > 1)


def _view_occupancy_diagnostics(
    pairs: tuple[tuple[str, str], ...], path: str
) -> tuple[Diagnostic, ...]:
    return tuple(
        _error("OBQ008", path, "generated BigQuery object-name collision", occupant[1])
        for occupant in _multi_occupants(pairs)
    )


def _node_view_collisions(domain: Domain) -> tuple[Diagnostic, ...]:
    pairs = tuple((node_view_name(domain.metadata.name, name), name) for name in domain.entities)
    return _view_occupancy_diagnostics(pairs, "spec.entities")


def _edge_view_collisions(domain: Domain) -> tuple[Diagnostic, ...]:
    pairs = tuple(
        (edge_view_name(domain.metadata.name, name), name) for name in domain.relationships
    )
    return _view_occupancy_diagnostics(pairs, "spec.relationships")


def _generated_views(domain: Domain) -> set[str]:
    domain_name = domain.metadata.name
    nodes = {node_view_name(domain_name, name) for name in domain.entities}
    edges = {edge_view_name(domain_name, name) for name in domain.relationships}
    return nodes | edges


def _graph_versus_view_collisions(domain: Domain) -> tuple[Diagnostic, ...]:
    graph = domain.bigquery.graph
    if graph not in _generated_views(domain):
        return ()
    return (
        _error(
            "OBQ008", "spec.bigquery.graph", "generated BigQuery object-name collision", (graph,)
        ),
    )


def _graph_element_alias_collisions(domain: Domain) -> tuple[Diagnostic, ...]:
    overlap = set(domain.entities) & set(domain.relationships)
    return tuple(
        _error(
            "OBQ008",
            f"spec.entities.{name}",
            "generated BigQuery object-name collision",
            (name,),
        )
        for name in sorted(overlap)
    )


def _append_unique(bucket: list[str], name: str) -> None:
    if name not in bucket:
        bucket.append(name)


def _casefold_groups(names: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    grouped: dict[str, list[str]] = {}
    for name in names:
        _append_unique(grouped.setdefault(name.casefold(), []), name)
    return tuple(tuple(sorted(bucket)) for bucket in grouped.values() if len(bucket) > 1)


def _casefold_collisions(names: tuple[str, ...], path: str) -> tuple[Diagnostic, ...]:
    return tuple(
        _error("OBQ008", path, "generated BigQuery object-name collision", group)
        for group in _casefold_groups(names)
    )


def _node_column_collisions(domain: Domain) -> tuple[Diagnostic, ...]:
    return tuple(
        item
        for name, entity in domain.entities.items()
        for item in _casefold_collisions(
            tuple(entity.properties), f"spec.entities.{name}.properties"
        )
    )


def _key_helpers(entity: EntityDefinition | None, namer: Callable[[str], str]) -> tuple[str, ...]:
    if entity is None:
        return ()
    return tuple(namer(name) for name in entity.key)


def _endpoint_helpers(domain: Domain, rel: RelationshipDefinition) -> tuple[str, ...]:
    from_cols = _key_helpers(domain.entities.get(rel.from_entity), from_key_column)
    to_cols = _key_helpers(domain.entities.get(rel.to_entity), to_key_column)
    return from_cols + to_cols


def _edge_view_aliases(domain: Domain, rel: RelationshipDefinition) -> tuple[str, ...]:
    helpers = _endpoint_helpers(domain, rel)
    keys = tuple(edge_key_column(index) for index in range(len(rel.mapping.key)))
    return keys + helpers + tuple(rel.properties)


def _edge_column_collisions(domain: Domain) -> tuple[Diagnostic, ...]:
    return tuple(
        item
        for name, rel in domain.relationships.items()
        for item in _casefold_collisions(
            _edge_view_aliases(domain, rel), f"spec.relationships.{name}"
        )
    )


def _object_name_collision_diagnostics(domain: Domain) -> tuple[Diagnostic, ...]:
    return (
        *_node_view_collisions(domain),
        *_edge_view_collisions(domain),
        *_graph_versus_view_collisions(domain),
        *_graph_element_alias_collisions(domain),
        *_node_column_collisions(domain),
        *_edge_column_collisions(domain),
    )


def validate_semantics(domain: Domain) -> tuple[Diagnostic, ...]:
    """Return every independent OBQ001-OBQ008 diagnostic for ``domain``.

    Performs no I/O and does not render SQL. Semantic failures are returned,
    never raised.
    """

    collected = (
        *_entity_key_diagnostics(domain),
        *_entity_property_set_diagnostics(domain),
        *_relationship_entity_diagnostics(domain),
        *_endpoint_key_diagnostics(domain),
        *_relationship_property_set_diagnostics(domain),
        *_reserved_name_diagnostics(domain),
        *_object_name_collision_diagnostics(domain),
    )
    return tuple(sorted(collected, key=_sort_key))
