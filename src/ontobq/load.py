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

"""Parse YAML/JSON Domain documents, structurally validate, and build typed IR."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ontobq.diagnostics import (
    STRUCTURAL_ERROR_CODE,
    Diagnostic,
    DomainLoadError,
    Severity,
)
from ontobq.ir import (
    BigQueryEntityMapping,
    BigQueryRelationshipMapping,
    BigQueryTarget,
    ColumnMapping,
    Domain,
    EntityDefinition,
    ExpressionMapping,
    MappingValue,
    Metadata,
    PropertyDefinition,
    PropertyType,
    RelationshipDefinition,
)
from ontobq.schema import load_v1alpha1_schema

_JSON_SUFFIX = ".json"
_YAML_SUFFIXES = {".yaml", ".yml"}


def load_domain(path: str | Path) -> Domain:
    """Load a Domain document from YAML or JSON after structural validation."""
    source = Path(path)
    document = parse_domain_file(source)
    diagnostics = structural_diagnostics(document)
    if diagnostics:
        raise DomainLoadError(diagnostics)
    return domain_from_document(document)


def parse_domain_file(path: Path) -> object:
    """Parse a Domain file into a JSON-compatible object."""
    _ensure_exists(path)
    parser = _parser_for_suffix(path.suffix.lower())
    return parser(path, path.read_text(encoding="utf-8"))


def structural_diagnostics(document: object) -> tuple[Diagnostic, ...]:
    """Return Draft 2020-12 structural diagnostics, ordered by path then message."""
    validator = Draft202012Validator(load_v1alpha1_schema())
    converted = [
        _validation_error_to_diagnostic(error) for error in validator.iter_errors(document)
    ]
    converted.sort(key=lambda item: (item.path, item.message))
    return tuple(converted)


def domain_from_document(document: object) -> Domain:
    """Deserialize a structurally valid document into typed IR."""
    payload = _as_mapping(document)
    spec = _as_mapping(payload["spec"])
    return Domain(
        api_version=str(payload["apiVersion"]),
        kind=str(payload["kind"]),
        metadata=_decode_metadata(_as_mapping(payload["metadata"])),
        bigquery=_decode_bigquery_target(_as_mapping(spec["bigquery"])),
        entities=_decode_entities(_as_mapping(spec["entities"])),
        relationships=_decode_relationships(_as_mapping(spec.get("relationships", {}))),
    )


def _ensure_exists(path: Path) -> None:
    if path.is_file():
        return
    raise DomainLoadError((_file_diagnostic(path, "domain file does not exist"),))


def _parser_for_suffix(suffix: str) -> Callable[[Path, str], object]:
    if suffix == _JSON_SUFFIX:
        return _parse_json
    if suffix in _YAML_SUFFIXES:
        return _parse_yaml
    diagnostic = Diagnostic(
        code=STRUCTURAL_ERROR_CODE,
        severity=Severity.ERROR,
        path="$",
        message=f"domain file must be .yaml, .yml, or .json, got {suffix}",
    )
    raise DomainLoadError((diagnostic,))


def _parse_json(path: Path, text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DomainLoadError((_file_diagnostic(path, f"invalid JSON: {exc.msg}"),)) from exc


def _parse_yaml(path: Path, text: str) -> object:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DomainLoadError((_file_diagnostic(path, f"invalid YAML: {exc}"),)) from exc


def _validation_error_to_diagnostic(error: ValidationError) -> Diagnostic:
    return Diagnostic(
        code=STRUCTURAL_ERROR_CODE,
        severity=Severity.ERROR,
        path=_jsonschema_path(error),
        message=error.message,
    )


def _jsonschema_path(error: ValidationError) -> str:
    json_path = error.json_path
    if json_path in {"$", "$.", ""}:
        return "$"
    if json_path.startswith("$."):
        return json_path[2:]
    return json_path.lstrip("$") or "$"


def _file_diagnostic(path: Path, message: str) -> Diagnostic:
    return Diagnostic(
        code=STRUCTURAL_ERROR_CODE,
        severity=Severity.ERROR,
        path="$",
        message=f"{path}: {message}",
    )


def _as_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, dict):
        return value
    raise TypeError(f"expected mapping, got {type(value).__name__}")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _decode_metadata(payload: Mapping[str, Any]) -> Metadata:
    return Metadata(
        name=str(payload["name"]),
        display_name=_optional_str(payload.get("displayName")),
        description=_optional_str(payload.get("description")),
    )


def _decode_bigquery_target(payload: Mapping[str, Any]) -> BigQueryTarget:
    return BigQueryTarget(
        project=str(payload["project"]),
        dataset=str(payload["dataset"]),
        graph=str(payload["graph"]),
    )


def _decode_property(payload: Mapping[str, Any]) -> PropertyDefinition:
    nullable = payload.get("nullable", True)
    return PropertyDefinition(type=PropertyType(str(payload["type"])), nullable=bool(nullable))


def _decode_properties(payload: Mapping[str, Any]) -> Mapping[str, PropertyDefinition]:
    decoded = {name: _decode_property(_as_mapping(body)) for name, body in payload.items()}
    return MappingProxyType(decoded)


def _decode_mapping_value(payload: Mapping[str, Any]) -> MappingValue:
    if "column" in payload:
        return ColumnMapping(column=str(payload["column"]))
    return ExpressionMapping(expression=str(payload["expression"]))


def _decode_mapping_values(payload: Mapping[str, Any]) -> Mapping[str, MappingValue]:
    decoded = {name: _decode_mapping_value(_as_mapping(body)) for name, body in payload.items()}
    return MappingProxyType(decoded)


def _decode_entity_mapping(payload: Mapping[str, Any]) -> BigQueryEntityMapping:
    return BigQueryEntityMapping(
        source=str(payload["source"]),
        properties=_decode_mapping_values(_as_mapping(payload["properties"])),
    )


def _decode_entity(payload: Mapping[str, Any]) -> EntityDefinition:
    mapping = _as_mapping(payload["mapping"])
    return EntityDefinition(
        key=tuple(str(part) for part in payload["key"]),
        properties=_decode_properties(_as_mapping(payload["properties"])),
        mapping=_decode_entity_mapping(_as_mapping(mapping["bigquery"])),
        description=_optional_str(payload.get("description")),
    )


def _decode_entities(payload: Mapping[str, Any]) -> Mapping[str, EntityDefinition]:
    decoded = {name: _decode_entity(_as_mapping(body)) for name, body in payload.items()}
    return MappingProxyType(decoded)


def _decode_relationship_mapping(payload: Mapping[str, Any]) -> BigQueryRelationshipMapping:
    raw_properties = payload.get("properties", {})
    return BigQueryRelationshipMapping(
        source=str(payload["source"]),
        key=tuple(_decode_mapping_value(_as_mapping(item)) for item in payload["key"]),
        from_endpoint=_decode_mapping_values(_as_mapping(payload["from"])),
        to_endpoint=_decode_mapping_values(_as_mapping(payload["to"])),
        properties=_decode_mapping_values(_as_mapping(raw_properties)),
    )


def _decode_relationship(payload: Mapping[str, Any]) -> RelationshipDefinition:
    mapping = _as_mapping(payload["mapping"])
    raw_properties = payload.get("properties", {})
    return RelationshipDefinition(
        from_entity=str(payload["from"]),
        to_entity=str(payload["to"]),
        mapping=_decode_relationship_mapping(_as_mapping(mapping["bigquery"])),
        properties=_decode_properties(_as_mapping(raw_properties)),
        description=_optional_str(payload.get("description")),
    )


def _decode_relationships(payload: Mapping[str, Any]) -> Mapping[str, RelationshipDefinition]:
    decoded = {name: _decode_relationship(_as_mapping(body)) for name, body in payload.items()}
    return MappingProxyType(decoded)
