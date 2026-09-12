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

"""Read-only data-integrity validation (OBQ201-OBQ206).

Layer 4 of RFC 8. Queries hit **source** mappings only: never compiled
``_ontobq_*`` views, ``__ontobq_*`` helpers, or ``PROPERTY GRAPH``.

Codes:

- ``OBQ201``: entity key contains NULL - ``spec.entities.<Name>.key``
- ``OBQ202``: entity key is not unique - ``spec.entities.<Name>.key``
- ``OBQ203``: relationship element key contains NULL -
  ``spec.relationships.<Name>.mapping.bigquery.key``
- ``OBQ204``: relationship element key is not unique -
  ``spec.relationships.<Name>.mapping.bigquery.key``
- ``OBQ205``: relationship source endpoint does not resolve to a node -
  ``spec.relationships.<Name>.mapping.bigquery.from``
- ``OBQ206``: relationship destination endpoint does not resolve to a node -
  ``spec.relationships.<Name>.mapping.bigquery.to``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

from ontobq.diagnostics import Diagnostic, Severity
from ontobq.ir import PropertyType
from ontobq.sql.interpolate import (
    quote_identifier,
    quote_resource,
    select_item,
    select_wrapped_item,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ontobq.bq.executor import BigQueryReadExecutor
    from ontobq.ir import Domain, EntityDefinition, MappingValue, RelationshipDefinition

DEFAULT_EVIDENCE_LIMIT = 20

_MESSAGES = {
    "OBQ201": "entity key contains NULL",
    "OBQ202": "entity key is not unique",
    "OBQ203": "relationship element key contains NULL",
    "OBQ204": "relationship element key is not unique",
    "OBQ205": "relationship source endpoint does not resolve to a node",
    "OBQ206": "relationship destination endpoint does not resolve to a node",
}

_GROUPABLE_WRAPPERS = {
    PropertyType.JSON: "TO_JSON_STRING",
    PropertyType.GEOGRAPHY: "ST_ASGEOJSON",
}


@dataclass(frozen=True)
class IntegrityQuery:
    """One deterministic read-only integrity SELECT.

    ``element`` is the semantic entity or relationship name. ``key_aliases``
    are projected violation-key columns in evidence order.
    """

    code: str
    path: str
    element: str
    sql: str
    evidence_limit: int
    key_aliases: tuple[str, ...]


@dataclass(frozen=True)
class IntegrityReport:
    """Compiled integrity queries plus diagnostics from execution."""

    queries: tuple[IntegrityQuery, ...]
    diagnostics: tuple[Diagnostic, ...]


class IntegrityExecutionError(Exception):
    """Raised when dry-run or query fails. Does not emit OBQ101-105."""

    def __init__(self, query: IntegrityQuery) -> None:
        self.query = query
        super().__init__(f"integrity query {query.code} for {query.element} failed at {query.path}")


class _SourceProjection(NamedTuple):
    """Inner SELECT against one mapping source."""

    source: str
    selects: tuple[str, ...]


def _grouped_sql(
    from_sql: str,
    keys: tuple[str, ...],
    where_sql: str,
    limit: int,
    having: str | None,
) -> str:
    select_keys = ",\n  ".join(keys)
    having_block = () if having is None else ("HAVING ", having, "\n")
    return "".join(
        (
            "SELECT\n  ",
            select_keys,
            ",\n  COUNT(*) AS violation_count,\n  COUNT(*) OVER() AS total_violations\n",
            from_sql,
            "\nWHERE ",
            where_sql,
            "\nGROUP BY\n  ",
            select_keys,
            "\n",
            *having_block,
            "ORDER BY\n  violation_count DESC,\n  ",
            select_keys,
            "\nLIMIT ",
            str(limit),
            "\n",
        )
    )


def _null_sql(inner: str, keys: tuple[str, ...], limit: int) -> str:
    where_sql = " OR ".join("".join((key, " IS NULL")) for key in keys)
    return _grouped_sql("FROM " + inner, keys, where_sql, limit, None)


def _unique_sql(inner: str, keys: tuple[str, ...], limit: int) -> str:
    where_sql = " AND ".join("".join((key, " IS NOT NULL")) for key in keys)
    return _grouped_sql("FROM " + inner, keys, where_sql, limit, "COUNT(*) > 1")


def _inner_from(source: str, selects: tuple[str, ...], alias: str) -> str:
    return "".join(
        (
            "(\n  SELECT\n    ",
            ",\n    ".join(selects),
            "\n  FROM ",
            quote_resource(source),
            "\n) AS ",
            alias,
        )
    )


def _property_type(entity: EntityDefinition, name: str) -> PropertyType | None:
    prop = entity.properties.get(name)
    if prop is None:
        return None
    return prop.type


def _select_for_property(value: MappingValue, alias: str, prop_type: PropertyType | None) -> str:
    wrapper = None if prop_type is None else _GROUPABLE_WRAPPERS.get(prop_type)
    if wrapper is None:
        return select_item(value, alias)
    return select_wrapped_item(wrapper, value, alias)


def _typed_selects(
    values: Mapping[str, MappingValue],
    entity: EntityDefinition,
    where: str,
) -> tuple[str, ...]:
    items = _mapped_items(values, entity.key, where)
    return tuple(
        _select_for_property(value, alias, _property_type(entity, alias)) for value, alias in items
    )


def _lookup(values: Mapping[str, MappingValue], name: str, where: str) -> MappingValue:
    value = values.get(name)
    if value is None:
        raise ValueError(f"missing {where} mapping for {name!r}")
    return value


def _mapped_items(
    values: Mapping[str, MappingValue],
    names: tuple[str, ...],
    where: str,
) -> tuple[tuple[MappingValue, str], ...]:
    if not names:
        raise ValueError(f"{where} must not be empty")
    return tuple((_lookup(values, name, where), name) for name in names)


def _qual(table: str, alias: str) -> str:
    return "".join((table, ".", quote_identifier(alias)))


def _qualified(table: str, aliases: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_qual(table, name) for name in aliases)


def _entity_queries(
    name: str, entity: EntityDefinition, limit: int
) -> tuple[IntegrityQuery, IntegrityQuery]:
    selects = _typed_selects(entity.mapping.properties, entity, "entity key")
    inner = _inner_from(entity.mapping.source, selects, "projected")
    keys = _qualified("projected", entity.key)
    path = f"spec.entities.{name}.key"
    return (
        IntegrityQuery("OBQ201", path, name, _null_sql(inner, keys, limit), limit, entity.key),
        IntegrityQuery("OBQ202", path, name, _unique_sql(inner, keys, limit), limit, entity.key),
    )


def _relationship_key_items(
    keys: tuple[MappingValue, ...],
) -> tuple[tuple[MappingValue, str], ...]:
    if not keys:
        raise ValueError("relationship mapping key must not be empty")
    return tuple((value, f"key_{index}") for index, value in enumerate(keys))


def _relationship_key_queries(
    name: str, relationship: RelationshipDefinition, limit: int
) -> tuple[IntegrityQuery, IntegrityQuery]:
    items = _relationship_key_items(relationship.mapping.key)
    aliases = tuple(alias for _, alias in items)
    selects = tuple(select_item(value, alias) for value, alias in items)
    inner = _inner_from(relationship.mapping.source, selects, "projected")
    keys = _qualified("projected", aliases)
    path = f"spec.relationships.{name}.mapping.bigquery.key"
    return (
        IntegrityQuery("OBQ203", path, name, _null_sql(inner, keys, limit), limit, aliases),
        IntegrityQuery("OBQ204", path, name, _unique_sql(inner, keys, limit), limit, aliases),
    )


def _orphan_sql(
    edge: _SourceProjection,
    node: _SourceProjection,
    aliases: tuple[str, ...],
    limit: int,
) -> str:
    on_sql = " AND ".join(
        "".join((_qual("edge", name), " = ", _qual("node", name))) for name in aliases
    )
    unmatched = " AND ".join("".join((_qual("node", name), " IS NULL")) for name in aliases)
    from_sql = "".join(
        (
            "FROM ",
            _inner_from(edge.source, edge.selects, "edge"),
            "\nLEFT JOIN ",
            _inner_from(node.source, node.selects, "node"),
            "\nON ",
            on_sql,
        )
    )
    return _grouped_sql(from_sql, _qualified("edge", aliases), unmatched, limit, None)


def _orphan_from_endpoint(
    edge_source: str,
    endpoint: Mapping[str, MappingValue],
    entity: EntityDefinition,
    where: str,
    limit: int,
) -> str:
    edge = _SourceProjection(edge_source, _typed_selects(endpoint, entity, where))
    node = _SourceProjection(
        entity.mapping.source,
        _typed_selects(entity.mapping.properties, entity, "entity key"),
    )
    return _orphan_sql(edge, node, entity.key, limit)


def _require_entity(domain: Domain, name: str) -> EntityDefinition:
    entity = domain.entities.get(name)
    if entity is None:
        raise ValueError(f"unknown entity {name!r}")
    return entity


def _source_orphan_query(
    domain: Domain, name: str, relationship: RelationshipDefinition, limit: int
) -> IntegrityQuery:
    entity = _require_entity(domain, relationship.from_entity)
    sql = _orphan_from_endpoint(
        relationship.mapping.source,
        relationship.mapping.from_endpoint,
        entity,
        "from-endpoint",
        limit,
    )
    path = f"spec.relationships.{name}.mapping.bigquery.from"
    return IntegrityQuery("OBQ205", path, name, sql, limit, entity.key)


def _dest_orphan_query(
    domain: Domain, name: str, relationship: RelationshipDefinition, limit: int
) -> IntegrityQuery:
    entity = _require_entity(domain, relationship.to_entity)
    sql = _orphan_from_endpoint(
        relationship.mapping.source,
        relationship.mapping.to_endpoint,
        entity,
        "to-endpoint",
        limit,
    )
    path = f"spec.relationships.{name}.mapping.bigquery.to"
    return IntegrityQuery("OBQ206", path, name, sql, limit, entity.key)


def _relationship_queries(
    domain: Domain, name: str, relationship: RelationshipDefinition, limit: int
) -> tuple[IntegrityQuery, ...]:
    null_key, unique_key = _relationship_key_queries(name, relationship, limit)
    return (
        null_key,
        unique_key,
        _source_orphan_query(domain, name, relationship, limit),
        _dest_orphan_query(domain, name, relationship, limit),
    )


def _require_limit(evidence_limit: int) -> int:
    if evidence_limit < 1:
        raise ValueError("evidence_limit must be >= 1")
    return evidence_limit


def compile_integrity_queries(
    domain: Domain, evidence_limit: int = DEFAULT_EVIDENCE_LIMIT
) -> tuple[IntegrityQuery, ...]:
    """Return OBQ201-OBQ206 SELECTs in IR insertion order.

    For each entity: OBQ201 then OBQ202. For each relationship: OBQ203, OBQ204,
    OBQ205, OBQ206. Identical IR and ``evidence_limit`` yield identical SQL.
    """

    limit = _require_limit(evidence_limit)
    entity_queries = tuple(
        query
        for name, entity in domain.entities.items()
        for query in _entity_queries(name, entity, limit)
    )
    relationship_queries = tuple(
        query
        for name, relationship in domain.relationships.items()
        for query in _relationship_queries(domain, name, relationship, limit)
    )
    return entity_queries + relationship_queries


def _render_evidence_value(value: object) -> str:
    if value is None:
        return "<NULL>"
    return str(value)


def _parse_int_text(value: str, field: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _parse_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    return _parse_int_text(value, field)


def _row_evidence(aliases: tuple[str, ...], row: Mapping[str, object]) -> str:
    keys = " ".join("".join((name, "=", _render_evidence_value(row.get(name)))) for name in aliases)
    count = _parse_int(row.get("violation_count"), "violation_count")
    return f"{keys} count={count}"


def _evidence(
    query: IntegrityQuery, rows: Sequence[Mapping[str, object]], total: int
) -> tuple[str, ...]:
    parts = [f"total_violations={total}"]
    parts.extend(_row_evidence(query.key_aliases, row) for row in rows)
    if total > len(rows):
        parts.append(f"truncated=true shown={len(rows)}")
    return tuple(parts)


def _diagnostic_from_rows(
    query: IntegrityQuery, rows: Sequence[Mapping[str, object]]
) -> Diagnostic | None:
    if not rows:
        return None
    total = _parse_int(rows[0].get("total_violations"), "total_violations")
    if total <= 0:
        return None
    return Diagnostic(
        code=query.code,
        severity=Severity.ERROR,
        path=query.path,
        message=_MESSAGES[query.code],
        evidence=_evidence(query, rows, total),
    )


def _run_query(executor: BigQueryReadExecutor, query: IntegrityQuery) -> Diagnostic | None:
    try:
        executor.dry_run(query.sql)
        rows = executor.query(query.sql, max_rows=query.evidence_limit)
        return _diagnostic_from_rows(query, rows)
    except Exception as exc:
        raise IntegrityExecutionError(query) from exc


def validate_integrity(
    domain: Domain,
    executor: BigQueryReadExecutor,
    *,
    evidence_limit: int = DEFAULT_EVIDENCE_LIMIT,
    execute: bool = True,
) -> IntegrityReport:
    """Compile integrity SELECTs and optionally execute them.

    When ``execute`` is false, return compiled SQL without calling ``executor``.
    When true, ``dry_run`` then ``query`` each statement. One diagnostic per
    ``(code, element)`` with ``total_violations > 0``. Evidence is bounded by
    ``evidence_limit``.
    """

    queries = compile_integrity_queries(domain, evidence_limit)
    if not execute:
        return IntegrityReport(queries=queries, diagnostics=())
    found = tuple(_run_query(executor, query) for query in queries)
    return IntegrityReport(queries=queries, diagnostics=tuple(item for item in found if item))
