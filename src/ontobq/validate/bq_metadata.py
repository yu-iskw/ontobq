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

"""Read-only BigQuery metadata validation (OBQ101-OBQ105).

``OBQ101``
    Mapped source does not exist or is an unsupported kind.
``OBQ102``
    Mapped source column does not exist.
``OBQ103``
    Trusted scalar mapping expression fails BigQuery dry-run/type analysis.
``OBQ104``
    Physical BigQuery value type is incompatible with the declared semantic type.
``OBQ105``
    Source and target BigQuery locations are incompatible.

Offline semantics ``OBQ001-OBQ008`` and integrity ``OBQ201-OBQ206`` are out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ontobq.bigquery.inspector import (
    ColumnSnapshot,
    canonicalize_bq_type,
    canonicalize_location,
    is_supported_source_kind,
)
from ontobq.diagnostics import Diagnostic, Severity
from ontobq.ir import ColumnMapping
from ontobq.validate.type_compat import physical_type_compatible

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ontobq.bigquery.inspector import (
        BigQueryInspector,
        ScalarDryRunResult,
        SourceSnapshot,
    )
    from ontobq.ir import (
        Domain,
        EntityDefinition,
        MappingValue,
        PropertyDefinition,
        PropertyType,
        RelationshipDefinition,
    )

OBQ101 = "OBQ101"
OBQ102 = "OBQ102"
OBQ103 = "OBQ103"
OBQ104 = "OBQ104"
OBQ105 = "OBQ105"


@dataclass(frozen=True)
class _Site:
    source: str
    path: str
    inspector: BigQueryInspector


class _CachedInspector:
    """Reuse source, column, and location lookups within one validation call."""

    def __init__(self, inner: BigQueryInspector) -> None:
        self._inner = inner
        self._sources: dict[str, SourceSnapshot] = {}
        self._columns: dict[str, tuple[ColumnSnapshot, ...]] = {}
        self._locations: dict[str, str | None] = {}

    def get_source(self, table_id: str) -> SourceSnapshot:
        if table_id not in self._sources:
            self._sources[table_id] = self._inner.get_source(table_id)
        return self._sources[table_id]

    def get_columns(self, table_id: str) -> tuple[ColumnSnapshot, ...]:
        if table_id not in self._columns:
            self._columns[table_id] = self._inner.get_columns(table_id)
        return self._columns[table_id]

    def dry_run_scalar_expression(self, source: str, expression: str) -> ScalarDryRunResult:
        return self._inner.dry_run_scalar_expression(source, expression)

    def get_location(self, resource: str) -> str | None:
        if resource not in self._locations:
            self._locations[resource] = self._inner.get_location(resource)
        return self._locations[resource]


def _error(code: str, path: str, message: str, evidence: tuple[str, ...]) -> Diagnostic:
    return Diagnostic(
        code=code, severity=Severity.ERROR, path=path, message=message, evidence=evidence
    )


def _obq101_missing(table_id: str, path: str) -> Diagnostic:
    return _error(
        OBQ101,
        path,
        f"mapped source {table_id!r} does not exist",
        (table_id,),
    )


def _obq101_unsupported(table_id: str, kind: str, path: str) -> Diagnostic:
    return _error(
        OBQ101,
        path,
        f"mapped source {table_id!r} has unsupported kind {kind!r}",
        (table_id, kind),
    )


def _source_existence(snapshot: SourceSnapshot, path: str) -> tuple[Diagnostic, ...]:
    if not snapshot.exists:
        return (_obq101_missing(snapshot.table_id, path),)
    if not is_supported_source_kind(snapshot.kind):
        return (_obq101_unsupported(snapshot.table_id, snapshot.kind, path),)
    return ()


def _obq105(
    path: str,
    table_id: str,
    source_loc: str | None,
    target_loc: str | None,
    target_id: str,
) -> Diagnostic:
    return _error(
        OBQ105,
        path,
        (
            f"source location {source_loc!r} is incompatible with target "
            f"dataset {target_id!r} location {target_loc!r}"
        ),
        (table_id, source_loc or "", target_id, target_loc or ""),
    )


def _location_diagnostics(
    snapshot: SourceSnapshot,
    path: str,
    domain: Domain,
    inspector: BigQueryInspector,
) -> tuple[Diagnostic, ...]:
    source_loc = canonicalize_location(snapshot.location)
    target_id = f"{domain.bigquery.project}.{domain.bigquery.dataset}"
    target_loc = canonicalize_location(inspector.get_location(target_id))
    if source_loc is not None and source_loc == target_loc:
        return ()
    return (_obq105(path, snapshot.table_id, source_loc, target_loc, target_id),)


def _source_diagnostics(site: _Site, domain: Domain) -> tuple[Diagnostic, ...]:
    snapshot = site.inspector.get_source(site.source)
    blocking = _source_existence(snapshot, f"{site.path}.source")
    if blocking:
        return blocking
    return _location_diagnostics(snapshot, f"{site.path}.source", domain, site.inspector)


def _obq104(path: str, semantic: PropertyType, physical: str, mode: str) -> Diagnostic:
    return _error(
        OBQ104,
        path,
        (
            f"physical BigQuery type {physical!r} (mode {mode!r}) is incompatible "
            f"with semantic type {semantic.value!r}"
        ),
        (semantic.value, physical, mode),
    )


def _type_diagnostics(
    path: str,
    semantic: PropertyType,
    physical: ColumnSnapshot,
) -> tuple[Diagnostic, ...]:
    canonical = canonicalize_bq_type(physical.type)
    if physical_type_compatible(semantic, canonical, physical.mode):
        return ()
    return (_obq104(path, semantic, canonical, physical.mode),)


def _optional_type_diagnostics(
    path: str,
    semantic: PropertyType | None,
    physical: ColumnSnapshot,
) -> tuple[Diagnostic, ...]:
    if semantic is None:
        return ()
    return _type_diagnostics(path, semantic, physical)


def _find_column(columns: tuple[ColumnSnapshot, ...], name: str) -> ColumnSnapshot | None:
    needle = name.lower()
    matches = tuple(column for column in columns if column.name.lower() == needle)
    if not matches:
        return None
    return matches[0]


def _obq102(path: str, table_id: str, column: str) -> Diagnostic:
    return _error(
        OBQ102,
        path,
        f"mapped source column {column!r} does not exist on {table_id!r}",
        (table_id, column),
    )


def _column_diagnostics(
    site: _Site,
    column: str,
    path: str,
    semantic: PropertyType | None,
) -> tuple[Diagnostic, ...]:
    physical = _find_column(site.inspector.get_columns(site.source), column)
    if physical is None:
        return (_obq102(path, site.source, column),)
    return _optional_type_diagnostics(path, semantic, physical)


def _probe_column(field_type: str | None) -> ColumnSnapshot:
    return ColumnSnapshot(name="__ontobq_type_probe", type=field_type or "", mode="NULLABLE")


def _obq103(path: str, expression: str, error: str | None) -> Diagnostic:
    detail = error or "dry-run failed"
    return _error(
        OBQ103,
        path,
        f"trusted scalar mapping expression failed BigQuery dry-run: {detail}",
        (expression, detail),
    )


def _expression_diagnostics(
    site: _Site,
    expression: str,
    path: str,
    semantic: PropertyType | None,
) -> tuple[Diagnostic, ...]:
    result = site.inspector.dry_run_scalar_expression(site.source, expression)
    if not result.ok:
        return (_obq103(path, expression, result.error),)
    physical = _probe_column(result.type)
    return _optional_type_diagnostics(path, semantic, physical)


def _mapping_diagnostics(
    site: _Site,
    mapping: MappingValue,
    path: str,
    semantic: PropertyType | None,
) -> tuple[Diagnostic, ...]:
    if isinstance(mapping, ColumnMapping):
        return _column_diagnostics(site, mapping.column, path, semantic)
    return _expression_diagnostics(site, mapping.expression, path, semantic)


def _declared_type(declared: Mapping[str, PropertyDefinition], name: str) -> PropertyType | None:
    prop = declared.get(name)
    if prop is None:
        return None
    return prop.type


def _flatten(parts: list[tuple[Diagnostic, ...]]) -> tuple[Diagnostic, ...]:
    return tuple(item for part in parts for item in part)


def _property_diagnostics(
    site: _Site,
    mapped: Mapping[str, MappingValue],
    declared: Mapping[str, PropertyDefinition],
) -> tuple[Diagnostic, ...]:
    parts = [
        _mapping_diagnostics(
            site, mapping, f"{site.path}.properties.{name}", _declared_type(declared, name)
        )
        for name, mapping in mapped.items()
    ]
    return _flatten(parts)


def _has_obq101(diagnostics: tuple[Diagnostic, ...]) -> bool:
    return any(item.code == OBQ101 for item in diagnostics)


def _validate_entity(
    domain: Domain,
    name: str,
    entity: EntityDefinition,
    inspector: BigQueryInspector,
) -> tuple[Diagnostic, ...]:
    site = _Site(entity.mapping.source, f"spec.entities.{name}.mapping.bigquery", inspector)
    source_diags = _source_diagnostics(site, domain)
    if _has_obq101(source_diags):
        return source_diags
    return source_diags + _property_diagnostics(site, entity.mapping.properties, entity.properties)


def _validate_entities(domain: Domain, inspector: BigQueryInspector) -> tuple[Diagnostic, ...]:
    parts = [
        _validate_entity(domain, name, entity, inspector)
        for name, entity in domain.entities.items()
    ]
    return _flatten(parts)


def _key_diagnostics(site: _Site, keys: tuple[MappingValue, ...]) -> tuple[Diagnostic, ...]:
    parts = [
        _mapping_diagnostics(site, mapping, f"{site.path}.key.{ordinal}", None)
        for ordinal, mapping in enumerate(keys)
    ]
    return _flatten(parts)


def _take_mapped(
    endpoint: Mapping[str, MappingValue],
    key_name: str,
    used: list[tuple[str, MappingValue]],
    seen: set[str],
) -> None:
    mapping = endpoint.get(key_name)
    if mapping is None:
        return
    used.append((key_name, mapping))
    seen.add(key_name)


def _take_remaining(
    name: str,
    mapping: MappingValue,
    used: list[tuple[str, MappingValue]],
    seen: set[str],
) -> None:
    if name in seen:
        return
    used.append((name, mapping))
    seen.add(name)


def _endpoint_items_for_keys(
    endpoint: Mapping[str, MappingValue],
    key_names: tuple[str, ...],
) -> tuple[tuple[str, MappingValue], ...]:
    used: list[tuple[str, MappingValue]] = []
    seen: set[str] = set()
    for key_name in key_names:
        _take_mapped(endpoint, key_name, used, seen)
    for name, mapping in endpoint.items():
        _take_remaining(name, mapping, used, seen)
    return tuple(used)


def _endpoint_items(
    endpoint: Mapping[str, MappingValue],
    entity: EntityDefinition | None,
) -> tuple[tuple[str, MappingValue], ...]:
    if entity is None:
        return tuple(endpoint.items())
    return _endpoint_items_for_keys(endpoint, entity.key)


def _endpoint_type(entity: EntityDefinition | None, name: str) -> PropertyType | None:
    if entity is None:
        return None
    return _declared_type(entity.properties, name)


def _endpoint_diagnostics(
    domain: Domain,
    entity_name: str,
    endpoint: Mapping[str, MappingValue],
    path: str,
    site: _Site,
) -> tuple[Diagnostic, ...]:
    entity = domain.entities.get(entity_name)
    parts = [
        _mapping_diagnostics(site, mapping, f"{path}.{name}", _endpoint_type(entity, name))
        for name, mapping in _endpoint_items(endpoint, entity)
    ]
    return _flatten(parts)


def _relationship_fields(
    domain: Domain,
    relationship: RelationshipDefinition,
    site: _Site,
) -> tuple[Diagnostic, ...]:
    mapping = relationship.mapping
    keys = _key_diagnostics(site, mapping.key)
    from_diags = _endpoint_diagnostics(
        domain, relationship.from_entity, mapping.from_endpoint, f"{site.path}.from", site
    )
    to_diags = _endpoint_diagnostics(
        domain, relationship.to_entity, mapping.to_endpoint, f"{site.path}.to", site
    )
    props = _property_diagnostics(site, mapping.properties, relationship.properties)
    return keys + from_diags + to_diags + props


def _validate_relationship(
    domain: Domain,
    name: str,
    relationship: RelationshipDefinition,
    inspector: BigQueryInspector,
) -> tuple[Diagnostic, ...]:
    site = _Site(
        relationship.mapping.source,
        f"spec.relationships.{name}.mapping.bigquery",
        inspector,
    )
    source_diags = _source_diagnostics(site, domain)
    if _has_obq101(source_diags):
        return source_diags
    return source_diags + _relationship_fields(domain, relationship, site)


def _validate_relationships(domain: Domain, inspector: BigQueryInspector) -> tuple[Diagnostic, ...]:
    parts = [
        _validate_relationship(domain, name, relationship, inspector)
        for name, relationship in domain.relationships.items()
    ]
    return _flatten(parts)


def validate_bigquery_metadata(
    domain: Domain,
    inspector: BigQueryInspector,
) -> tuple[Diagnostic, ...]:
    """Return Layer 3 diagnostics for every mapped source, column, and expression."""

    scoped = _CachedInspector(inspector)
    entity_diags = _validate_entities(domain, scoped)
    relationship_diags = _validate_relationships(domain, scoped)
    return entity_diags + relationship_diags
