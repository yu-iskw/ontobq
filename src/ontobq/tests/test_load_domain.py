"""Loader tests: YAML/JSON parse, structural validation, typed Domain IR."""

from __future__ import annotations

import pytest  # pyright: ignore[reportMissingImports]

from ontobq import ColumnMapping, Domain, DomainLoadError, ExpressionMapping, load_domain
from ontobq.tests.paths import EXAMPLES_DIR, FIXTURES_DIR


def test_load_domain_yaml_commerce() -> None:
    domain = load_domain(EXAMPLES_DIR / "commerce.yaml")
    assert isinstance(domain, Domain)
    assert domain.api_version == "ontobq.dev/v1alpha1"
    assert domain.kind == "Domain"
    assert domain.metadata.name == "commerce"
    assert set(domain.entities) == {"Customer", "Order"}
    assert set(domain.relationships) == {"PLACED"}


def test_load_domain_json_commerce() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.json")
    assert isinstance(domain, Domain)
    assert domain.entities["Customer"].mapping.source == "my-project.raw.customers"


def test_load_domain_yaml_and_json_equivalent() -> None:
    yaml_domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    json_domain = load_domain(FIXTURES_DIR / "commerce.json")
    assert yaml_domain == json_domain


def test_load_domain_column_mapping() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    mapping = domain.entities["Customer"].mapping.properties["id"]
    assert isinstance(mapping, ColumnMapping)
    assert mapping.column == "customer_id"


def test_load_domain_expression_mapping() -> None:
    domain = load_domain(FIXTURES_DIR / "expression-mapping.yaml")
    mapping = domain.entities["Order"].mapping.properties["createdAt"]
    assert isinstance(mapping, ExpressionMapping)
    assert mapping.expression == "TIMESTAMP(created_at)"


def test_load_domain_composite_key() -> None:
    domain = load_domain(FIXTURES_DIR / "composite-key.yaml")
    assert domain.entities["Customer"].key == ("tenantId", "id")


def test_load_invalid_unknown_field_diagnostic_path() -> None:
    with pytest.raises(DomainLoadError, match="OBQ000") as caught:
        load_domain(FIXTURES_DIR / "invalid-unknown-nested.yaml")
    joined = " ".join(f"{item.path} {item.message}" for item in caught.value.diagnostics)
    assert "unexpected" in joined


def test_load_domain_returns_typed_ir_not_dict() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    assert isinstance(domain, Domain)
    assert not isinstance(domain, dict)
    placed = domain.relationships["PLACED"]
    assert placed.from_entity == "Customer"
    assert placed.to_entity == "Order"
    edge_key = placed.mapping.key[0]
    assert isinstance(edge_key, ColumnMapping)
    assert edge_key.column == "order_id"
