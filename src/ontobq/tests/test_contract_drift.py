"""Contract tests that keep the JSON Schema and typed IR aligned."""

from __future__ import annotations

from dataclasses import fields

from ontobq.ir import (
    BigQueryEntityMapping,
    BigQueryRelationshipMapping,
    BigQueryTarget,
    ColumnMapping,
    Domain,
    EntityDefinition,
    ExpressionMapping,
    Metadata,
    PropertyDefinition,
    PropertyType,
    RelationshipDefinition,
)
from ontobq.schema import load_v1alpha1_schema


def test_property_type_enum_matches_schema_no_drift() -> None:
    schema_enum = load_v1alpha1_schema()["$defs"]["PropertyType"]["enum"]
    assert [item.value for item in PropertyType] == schema_enum


def test_schema_ir_contract_metadata_fields() -> None:
    schema_props = set(load_v1alpha1_schema()["$defs"]["Metadata"]["properties"])
    ir_fields = {item.name for item in fields(Metadata)}
    assert schema_props == {"name", "displayName", "description"}
    assert ir_fields == {"name", "display_name", "description"}


def test_schema_ir_contract_domain_spec_fields() -> None:
    schema_props = set(load_v1alpha1_schema()["$defs"]["Spec"]["properties"])
    ir_fields = {item.name for item in fields(Domain)}
    assert schema_props == {"bigquery", "entities", "relationships"}
    assert {"bigquery", "entities", "relationships"}.issubset(ir_fields)


def test_schema_ir_contract_entity_and_relationship_types() -> None:
    assert {item.name for item in fields(EntityDefinition)} == {
        "key",
        "properties",
        "mapping",
        "description",
    }
    assert {item.name for item in fields(RelationshipDefinition)} == {
        "from_entity",
        "to_entity",
        "mapping",
        "properties",
        "description",
    }
    assert {item.name for item in fields(BigQueryTarget)} == {"project", "dataset", "graph"}
    assert {item.name for item in fields(PropertyDefinition)} == {"type", "nullable"}
    assert {item.name for item in fields(BigQueryEntityMapping)} == {"source", "properties"}
    assert {item.name for item in fields(BigQueryRelationshipMapping)} == {
        "source",
        "key",
        "from_endpoint",
        "to_endpoint",
        "properties",
    }
    assert {item.name for item in fields(ColumnMapping)} == {"column"}
    assert {item.name for item in fields(ExpressionMapping)} == {"expression"}
