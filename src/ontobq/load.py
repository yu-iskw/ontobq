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
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, NamedTuple

import yaml
from jsonschema import Draft202012Validator

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

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from jsonschema.exceptions import ValidationError

_JSON_SUFFIX = ".json"
_YAML_SUFFIXES = {".yaml", ".yml"}


class _DuplicateMappingKeyError(ValueError):
    """A mapping repeated a key during JSON or YAML parse."""

    def __init__(self, path: tuple[str, ...]) -> None:
        self.path = path
        super().__init__(".".join(path) if path else "$")


class _JsonMap(NamedTuple):
    """JSON object preserved as pairs so duplicate keys remain visible."""

    pairs: tuple[tuple[Any, Any], ...]


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """SafeLoader that rejects repeated mapping keys."""

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self._mapping_path: list[str] = []

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[Any, Any]:
        self.flatten_mapping(node)
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            mapping[key] = self._construct_unique_value(mapping, key, value_node, deep)
        return mapping

    def _construct_unique_value(
        self,
        mapping: dict[Any, Any],
        key: object,
        value_node: Any,
        deep: bool,
    ) -> object:
        rendered = str(key)
        key_path = (*self._mapping_path, rendered)
        if key in mapping:
            raise _DuplicateMappingKeyError(key_path)
        self._mapping_path.append(rendered)
        try:
            return self.construct_object(value_node, deep=deep)
        finally:
            self._mapping_path.pop()


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
    return parser(path, _read_utf8_text(path))


def structural_diagnostics(document: object) -> tuple[Diagnostic, ...]:
    """Return Draft 2020-12 structural diagnostics, ordered by path then message."""
    instance: Any = document
    validator = Draft202012Validator(load_v1alpha1_schema())
    converted = [
        _validation_error_to_diagnostic(error) for error in validator.iter_errors(instance)
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
        loaded = json.loads(text, object_pairs_hook=_json_object_pairs)
    except json.JSONDecodeError as exc:
        raise DomainLoadError((_file_diagnostic(path, f"invalid JSON: {exc.msg}"),)) from exc
    try:
        return _materialize_json(loaded, ())
    except _DuplicateMappingKeyError as exc:
        raise _duplicate_key_error(path, exc.path) from exc


def _parse_yaml(path: Path, text: str) -> object:
    try:
        return _load_unique_yaml(text)
    except _DuplicateMappingKeyError as exc:
        raise _duplicate_key_error(path, exc.path) from exc
    except yaml.YAMLError as exc:
        raise DomainLoadError((_file_diagnostic(path, f"invalid YAML: {exc}"),)) from exc


def _load_unique_yaml(text: str) -> object:
    loader = _UniqueKeySafeLoader(text)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _validation_error_to_diagnostic(error: ValidationError) -> Diagnostic:
    return Diagnostic(
        code=STRUCTURAL_ERROR_CODE,
        severity=Severity.ERROR,
        path=_jsonschema_path(error),
        message=error.message,
    )


def _jsonschema_path(error: ValidationError) -> str:
    components = [str(part) for part in error.absolute_path]
    if not components:
        return "$"
    return ".".join(components)


def _read_utf8_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DomainLoadError((_file_diagnostic(path, str(exc)),)) from exc


def _json_object_pairs(pairs: list[tuple[Any, Any]]) -> _JsonMap:
    return _JsonMap(tuple(pairs))


def _materialize_json(value: object, path: tuple[str, ...]) -> object:
    if isinstance(value, _JsonMap):
        return _materialize_json_map(value, path)
    if isinstance(value, list):
        return [_materialize_json(item, (*path, str(index))) for index, item in enumerate(value)]
    return value


def _materialize_json_map(value: _JsonMap, path: tuple[str, ...]) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key, child in value.pairs:
        if key in mapping:
            raise _DuplicateMappingKeyError((*path, str(key)))
        mapping[key] = _materialize_json(child, (*path, str(key)))
    return mapping


def _duplicate_key_error(path: Path, key_path: tuple[str, ...]) -> DomainLoadError:
    location = ".".join(key_path) if key_path else "$"
    diagnostic = Diagnostic(
        code=STRUCTURAL_ERROR_CODE,
        severity=Severity.ERROR,
        path=location,
        message=f"{path}: duplicate mapping key",
    )
    return DomainLoadError((diagnostic,))


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
