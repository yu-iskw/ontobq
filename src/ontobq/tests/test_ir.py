"""Typed IR class presence used by downstream compilers."""

from __future__ import annotations

from ontobq.ir import (
    BigQueryEntityMapping,
    BigQueryRelationshipMapping,
    BigQueryTarget,
    Domain,
    EntityDefinition,
    Metadata,
    PropertyDefinition,
    RelationshipDefinition,
)
from ontobq.load import load_domain
from ontobq.tests.paths import FIXTURES_DIR


def test_ir_domain_types() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    assert isinstance(domain, Domain)
    assert isinstance(domain.metadata, Metadata)
    assert isinstance(domain.bigquery, BigQueryTarget)


def test_ir_metadata() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    assert domain.metadata.display_name == "Commerce"


def test_ir_bigquery_target() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    assert domain.bigquery.graph == "commerce_graph"


def test_ir_entity_definition() -> None:
    entity = load_domain(FIXTURES_DIR / "commerce.yaml").entities["Customer"]
    assert isinstance(entity, EntityDefinition)
    assert entity.key == ("id",)


def test_ir_property_definition() -> None:
    entity = load_domain(FIXTURES_DIR / "commerce.yaml").entities["Customer"]
    prop = entity.properties["id"]
    assert isinstance(prop, PropertyDefinition)
    assert prop.nullable is False


def test_ir_entity_mapping() -> None:
    mapping = load_domain(FIXTURES_DIR / "commerce.yaml").entities["Customer"].mapping
    assert isinstance(mapping, BigQueryEntityMapping)


def test_ir_relationship_definition() -> None:
    rel = load_domain(FIXTURES_DIR / "commerce.yaml").relationships["PLACED"]
    assert isinstance(rel, RelationshipDefinition)


def test_ir_relationship_mapping() -> None:
    mapping = load_domain(FIXTURES_DIR / "commerce.yaml").relationships["PLACED"].mapping
    assert isinstance(mapping, BigQueryRelationshipMapping)
    assert "id" in mapping.from_endpoint
    assert "id" in mapping.to_endpoint
