"""JSON Schema contract tests for ontobq.dev/v1alpha1."""

from __future__ import annotations

import json

import pytest  # pyright: ignore[reportMissingImports]
import yaml
from jsonschema import Draft202012Validator

from ontobq.load import DomainLoadError, load_domain, structural_diagnostics
from ontobq.schema import API_VERSION, KIND, SCHEMA_ID, load_v1alpha1_schema
from ontobq.tests.paths import EXAMPLES_DIR, FIXTURES_DIR, SCHEMA_PATH


def _load_yaml(name: str) -> object:
    path = FIXTURES_DIR / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_schema_exists_at_stable_path() -> None:
    assert SCHEMA_PATH.is_file()
    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert payload["$id"] == SCHEMA_ID


def test_schema_draft_2020_12() -> None:
    schema = load_v1alpha1_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_schema_id() -> None:
    assert load_v1alpha1_schema()["$id"] == "https://ontobq.dev/schemas/v1alpha1.json"


def test_schema_api_version_constant() -> None:
    schema = load_v1alpha1_schema()
    assert schema["properties"]["apiVersion"]["const"] == API_VERSION


def test_schema_kind_constant() -> None:
    schema = load_v1alpha1_schema()
    assert schema["properties"]["kind"]["const"] == KIND


def test_schema_commerce_validates_with_draft202012() -> None:
    document = yaml.safe_load((EXAMPLES_DIR / "commerce.yaml").read_text(encoding="utf-8"))
    Draft202012Validator(load_v1alpha1_schema()).validate(document)


def test_schema_unknown_field_at_root_fails() -> None:
    diagnostics = structural_diagnostics(_load_yaml("invalid-unknown-root.yaml"))
    assert diagnostics
    joined = " ".join(f"{item.path} {item.message}" for item in diagnostics)
    assert "unexpected" in joined


def test_schema_unknown_field_nested_additional_properties_fail() -> None:
    diagnostics = structural_diagnostics(_load_yaml("invalid-unknown-nested.yaml"))
    assert diagnostics
    joined = " ".join(f"{item.path} {item.message}" for item in diagnostics)
    assert "unexpected" in joined
    assert "Customer" in joined or "entities" in joined


def test_schema_mapping_cannot_contain_both_column_and_expression() -> None:
    diagnostics = structural_diagnostics(_load_yaml("invalid-column-and-expression.yaml"))
    assert diagnostics


def test_schema_property_type_enum() -> None:
    expected = [
        "string",
        "integer",
        "number",
        "boolean",
        "date",
        "datetime",
        "time",
        "timestamp",
        "bytes",
        "json",
        "geography",
    ]
    assert load_v1alpha1_schema()["$defs"]["PropertyType"]["enum"] == expected


def test_schema_unsupported_property_type_enum_fails() -> None:
    diagnostics = structural_diagnostics(_load_yaml("invalid-property-type.yaml"))
    assert diagnostics


def test_schema_identifier_name_pattern() -> None:
    diagnostics = structural_diagnostics(_load_yaml("invalid-identifier.yaml"))
    assert diagnostics
    joined = " ".join(f"{item.path} {item.message}" for item in diagnostics)
    assert "commerce-domain" in joined or "name" in joined


def test_schema_unknown_entity_ref_still_structurally_valid() -> None:
    load_domain(FIXTURES_DIR / "unknown-entity-ref.yaml")


def test_schema_object_defs_forbid_additional_properties() -> None:
    schema = load_v1alpha1_schema()
    assert schema["additionalProperties"] is False
    for name, definition in schema["$defs"].items():
        if definition.get("type") != "object":
            continue
        if "properties" not in definition:
            continue
        assert definition.get("additionalProperties") is False, name


def test_load_invalid_kind_fails() -> None:
    with pytest.raises(DomainLoadError, match="OBQ000"):
        load_domain(FIXTURES_DIR / "invalid-kind.yaml")
