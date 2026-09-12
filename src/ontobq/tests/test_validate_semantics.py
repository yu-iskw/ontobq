"""Offline semantic validation OBQ001-OBQ008 over typed Domain IR."""

from __future__ import annotations

import ast
from pathlib import Path

import ontobq
from ontobq import (
    BigQueryEntityMapping,
    BigQueryTarget,
    ColumnMapping,
    Diagnostic,
    Domain,
    EntityDefinition,
    Metadata,
    PropertyDefinition,
    PropertyType,
    Severity,
    load_domain,
    node_view_name,
    semantics as semantics_module,
    validate_semantics,
)
from ontobq.tests.paths import FIXTURES_DIR

SEMANTICS_DIR = FIXTURES_DIR / "semantics"


def _load_semantics(name: str) -> Domain:
    return load_domain(SEMANTICS_DIR / name)


def _codes(diagnostics: tuple[Diagnostic, ...]) -> tuple[str, ...]:
    return tuple(item.code for item in diagnostics)


def _assert_single_code(domain: Domain, code: str) -> tuple[Diagnostic, ...]:
    diagnostics = validate_semantics(domain)
    assert _codes(diagnostics)
    assert set(_codes(diagnostics)) == {code}
    assert all(item.severity is Severity.ERROR for item in diagnostics)
    return diagnostics


def _assert_no_diagnostics(diagnostics: tuple[Diagnostic, ...]) -> None:
    assert isinstance(diagnostics, tuple)
    assert len(diagnostics) == 0


def test_commerce_yaml_is_semantically_valid() -> None:
    _assert_no_diagnostics(validate_semantics(load_domain(FIXTURES_DIR / "commerce.yaml")))


def test_commerce_json_is_semantically_valid() -> None:
    _assert_no_diagnostics(validate_semantics(load_domain(FIXTURES_DIR / "commerce.json")))


def test_expression_mapping_is_semantically_valid() -> None:
    _assert_no_diagnostics(
        validate_semantics(load_domain(FIXTURES_DIR / "expression-mapping.yaml"))
    )


def test_composite_endpoints_are_semantically_valid() -> None:
    domain = _load_semantics("composite-endpoints.yaml")
    assert domain.entities["Customer"].key == ("tenantId", "id")
    assert set(domain.relationships["PLACED"].mapping.from_endpoint) == {"tenantId", "id"}
    _assert_no_diagnostics(validate_semantics(domain))


def test_validate_semantics_is_deterministic() -> None:
    domain = _load_semantics("multi-error.yaml")
    first = validate_semantics(domain)
    second = validate_semantics(domain)
    assert first == second
    assert _codes(first) == tuple(sorted(_codes(first)))


def test_obq001_unknown_key_property() -> None:
    diagnostics = _assert_single_code(_load_semantics("obq001-unknown-key-property.yaml"), "OBQ001")
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "spec.entities.Customer.key"
    assert diagnostics[0].evidence == ("missing",)


def test_obq002_entity_property_set_mismatch() -> None:
    diagnostics = _assert_single_code(
        _load_semantics("obq002-entity-property-set-mismatch.yaml"), "OBQ002"
    )
    assert diagnostics[0].path == "spec.entities.Customer.mapping.bigquery.properties"
    assert diagnostics[0].evidence == ("name",)


def test_obq003_unknown_from_entity_skips_obq005() -> None:
    diagnostics = _assert_single_code(
        load_domain(FIXTURES_DIR / "unknown-entity-ref.yaml"), "OBQ003"
    )
    assert diagnostics[0].path == "spec.relationships.POINTS_AT.from"
    assert not any(item.path.endswith(".from") and item.code == "OBQ005" for item in diagnostics)


def test_obq004_unknown_to_entity_skips_obq005() -> None:
    diagnostics = _assert_single_code(_load_semantics("obq004-unknown-to-entity.yaml"), "OBQ004")
    assert diagnostics[0].path == "spec.relationships.POINTS_AT.to"
    assert not any(item.path.endswith(".to") and item.code == "OBQ005" for item in diagnostics)


def test_obq005_composite_endpoint_missing_key() -> None:
    diagnostics = _assert_single_code(
        _load_semantics("obq005-endpoint-key-mismatch.yaml"), "OBQ005"
    )
    assert diagnostics[0].path.endswith("mapping.bigquery.from")
    assert diagnostics[0].path == "spec.relationships.PLACED.mapping.bigquery.from"
    assert "tenantId" in diagnostics[0].evidence


def test_obq005_extra_endpoint_key() -> None:
    diagnostics = _assert_single_code(_load_semantics("obq005-extra-endpoint-key.yaml"), "OBQ005")
    assert diagnostics[0].path.endswith("mapping.bigquery.from")
    assert diagnostics[0].evidence == ("extraId",)


def test_obq006_relationship_property_set_mismatch() -> None:
    diagnostics = _assert_single_code(
        _load_semantics("obq006-relationship-property-set-mismatch.yaml"), "OBQ006"
    )
    assert diagnostics[0].path == "spec.relationships.PLACED.mapping.bigquery.properties"
    assert diagnostics[0].evidence == ("placedAt",)


def _customer_only_domain(graph: str) -> Domain:
    entity = EntityDefinition(
        key=("id",),
        properties={"id": PropertyDefinition(type=PropertyType.STRING, nullable=False)},
        mapping=BigQueryEntityMapping(
            source="my-project.raw.customers",
            properties={"id": ColumnMapping(column="customer_id")},
        ),
    )
    return Domain(
        api_version="ontobq.dev/v1alpha1",
        kind="Domain",
        metadata=Metadata(name="commerce"),
        bigquery=BigQueryTarget(project="my-project", dataset="semantic", graph=graph),
        entities={"Customer": entity},
        relationships={},
    )


def test_obq007_reserved_graph_name() -> None:
    # After #20, spec.bigquery.graph is an Identifier, so reserved names are IR-only.
    diagnostics = _assert_single_code(_customer_only_domain("__ontobq_reserved"), "OBQ007")
    assert diagnostics[0].path == "spec.bigquery.graph"
    assert diagnostics[0].evidence == ("__ontobq_reserved",)


def _reserved_property_domain() -> Domain:
    reserved = "__ontobq_from_id"
    entity = EntityDefinition(
        key=("id",),
        properties={
            "id": PropertyDefinition(type=PropertyType.STRING, nullable=False),
            reserved: PropertyDefinition(type=PropertyType.STRING),
        },
        mapping=BigQueryEntityMapping(
            source="my-project.raw.customers",
            properties={
                "id": ColumnMapping(column="customer_id"),
                reserved: ColumnMapping(column="helper"),
            },
        ),
    )
    return Domain(
        api_version="ontobq.dev/v1alpha1",
        kind="Domain",
        metadata=Metadata(name="commerce"),
        bigquery=BigQueryTarget(project="my-project", dataset="semantic", graph="commerce_graph"),
        entities={"Customer": entity},
        relationships={},
    )


def test_obq007_reserved_property_name_in_memory() -> None:
    diagnostics = _assert_single_code(_reserved_property_domain(), "OBQ007")
    assert any(
        item.path.startswith("spec.entities.Customer.properties")
        and "__ontobq_from_id" in item.evidence
        for item in diagnostics
    )


def test_obq008_casefold_entity_view_collision() -> None:
    domain = _load_semantics("obq008-casefold-entities.yaml")
    assert set(domain.entities) == {"Customer", "customer"}
    assert node_view_name("commerce", "Customer") == node_view_name("commerce", "customer")
    diagnostics = _assert_single_code(domain, "OBQ008")
    assert len(diagnostics) == 1
    assert "Customer" in diagnostics[0].evidence
    assert "customer" in diagnostics[0].evidence


def test_obq008_graph_element_alias_collision() -> None:
    diagnostics = _assert_single_code(_load_semantics("obq008-alias-collision.yaml"), "OBQ008")
    assert diagnostics[0].evidence == ("PLACED",)


def test_obq008_graph_element_alias_casefold_collision() -> None:
    domain = _load_semantics("obq008-alias-casefold.yaml")
    assert set(domain.entities) == {"Customer"}
    assert set(domain.relationships) == {"customer"}
    diagnostics = _assert_single_code(domain, "OBQ008")
    assert "Customer" in diagnostics[0].evidence
    assert "customer" in diagnostics[0].evidence


def test_obq008_graph_name_collides_with_view() -> None:
    view = node_view_name("commerce", "Customer")
    diagnostics = validate_semantics(_customer_only_domain(view))
    collisions = [item for item in diagnostics if item.code == "OBQ008"]
    assert collisions
    assert any(item.path == "spec.bigquery.graph" for item in collisions)
    assert view in {
        token for item in collisions for token in (*item.evidence, item.path, item.message)
    }


def test_obq008_property_casefold_collision() -> None:
    diagnostics = _assert_single_code(_load_semantics("obq008-property-casefold.yaml"), "OBQ008")
    assert "status" in diagnostics[0].evidence
    assert "Status" in diagnostics[0].evidence


def test_multi_error_returns_independent_codes() -> None:
    diagnostics = validate_semantics(_load_semantics("multi-error.yaml"))
    assert set(_codes(diagnostics)) == {"OBQ001", "OBQ003"}
    assert diagnostics == tuple(
        sorted(diagnostics, key=lambda item: (item.code, item.path, item.message, item.evidence))
    )


def test_validate_semantics_performs_no_io_and_imports_no_bigquery() -> None:
    module_file = semantics_module.__file__
    assert module_file is not None
    text = Path(module_file).read_text(encoding="utf-8")
    assert "google.cloud" not in text
    assert "from google" not in text
    assert "open(" not in text
    assert "Path(" not in text
    assert "compile_mapping_views" not in text
    tree = ast.parse(text)
    defined = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    assert "node_view_name" not in defined
    assert "validate_semantics" in defined


def test_validate_semantics_is_exported() -> None:
    assert "validate_semantics" in ontobq.__all__
    assert ontobq.validate_semantics is validate_semantics
