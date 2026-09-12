"""Property-graph DDL compiler tests against Domain IR fixtures and artifacts."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest  # pyright: ignore[reportMissingImports]

from ontobq import (
    BigQueryEntityMapping,
    BigQueryRelationshipMapping,
    BigQueryTarget,
    ColumnMapping,
    Domain,
    EntityDefinition,
    MappingViewArtifact,
    Metadata,
    PropertyDefinition,
    PropertyType,
    RelationshipDefinition,
    compile_mapping_views,
    compile_property_graph,
    load_domain,
)
from ontobq.compile import property_graph as property_graph_module
from ontobq.tests.paths import FIXTURES_DIR, TESTS_DIR

if TYPE_CHECKING:
    from ontobq.compile.property_graph import PropertyGraphArtifact

_GOLDENS = TESTS_DIR / "goldens" / "property_graph"
_PHYSICAL_IDENTIFIERS = ("customer_id", "customer_name", "created_at", "order_id")


def _golden(name: str) -> str:
    return (_GOLDENS / name).read_text(encoding="utf-8")


def _compile(domain: Domain) -> PropertyGraphArtifact:
    return compile_property_graph(domain, compile_mapping_views(domain))


def test_commerce_graph_golden() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    artifact = _compile(domain)
    assert artifact.semantic_name == "commerce"
    assert artifact.graph_name == "commerce_graph"
    assert artifact.qualified_name == "my-project.semantic.commerce_graph"
    assert artifact.sql == _golden("commerce.sql")


def test_commerce_nodes_use_semantic_aliases_and_keys() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    views = compile_mapping_views(domain)
    artifact = compile_property_graph(domain, views)
    customer = _artifact(views, "Customer")
    order = _artifact(views, "Order")
    sql = artifact.sql
    assert f"`{customer.qualified_name}`" in sql
    assert f"`{order.qualified_name}`" in sql
    assert "AS Customer" in sql
    assert "AS Order" in sql
    assert "LABEL Customer" in sql
    assert "LABEL Order" in sql
    assert "KEY (id)" in sql
    assert "PROPERTIES (id, name, country)" in sql
    assert "PROPERTIES (id, createdAt, status)" in sql
    assert customer.output_columns == tuple(domain.entities["Customer"].properties)


def test_commerce_placed_edge_uses_helpers_and_semantic_properties() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    views = compile_mapping_views(domain)
    placed = _artifact(views, "PLACED")
    sql = compile_property_graph(domain, views).sql
    assert f"`{placed.qualified_name}`" in sql
    assert "AS PLACED" in sql
    assert "LABEL PLACED" in sql
    assert "KEY (__ontobq_edge_key_0)" in sql
    assert "SOURCE KEY (__ontobq_from_id)" in sql
    assert "REFERENCES Customer (id)" in sql
    assert "DESTINATION KEY (__ontobq_to_id)" in sql
    assert "REFERENCES Order (id)" in sql
    assert "PROPERTIES (placedAt)" in sql
    assert "created_at" not in sql
    helper_count = len(placed.edge_key_columns) + len(placed.from_columns) + len(placed.to_columns)
    semantic_tail = placed.output_columns[helper_count:]
    assert tuple(domain.relationships["PLACED"].properties) == semantic_tail


def test_composite_customer_node_key_golden() -> None:
    domain = load_domain(FIXTURES_DIR / "composite-key.yaml")
    artifact = _compile(domain)
    assert "KEY (tenantId, id)" in artifact.sql
    assert "EDGE TABLES" not in artifact.sql
    assert artifact.sql == _golden("composite_customer.sql")


def test_composite_contains_keys_and_empty_edge_properties() -> None:
    domain = _line_item_domain()
    views = compile_mapping_views(domain)
    contains = _artifact(views, "CONTAINS")
    artifact = compile_property_graph(domain, views)
    sql = artifact.sql
    assert "KEY (orderId, sku)" in sql
    assert "KEY (__ontobq_edge_key_0, __ontobq_edge_key_1)" in sql
    assert "DESTINATION KEY (__ontobq_to_orderId, __ontobq_to_sku)" in sql
    assert "REFERENCES LineItem (orderId, sku)" in sql
    assert "PROPERTIES (" not in sql.split("AS CONTAINS", 1)[1]
    helpers = contains.edge_key_columns + contains.from_columns + contains.to_columns
    assert contains.output_columns == helpers
    assert not domain.relationships["CONTAINS"].properties
    assert artifact.sql == _golden("composite_contains.sql")


def test_sql_contains_no_raw_source_columns() -> None:
    sql = _compile(load_domain(FIXTURES_DIR / "commerce.yaml")).sql
    for name in _PHYSICAL_IDENTIFIERS:
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])"
        assert re.search(pattern, sql) is None, name


def test_expression_mapping_fixture_uses_semantic_names_only() -> None:
    sql = _compile(load_domain(FIXTURES_DIR / "expression-mapping.yaml")).sql
    assert "PROPERTIES (id, createdAt)" in sql
    assert "TIMESTAMP" not in sql
    assert "created_at" not in sql
    assert "CREATE OR REPLACE VIEW" not in sql
    assert "SELECT" not in sql


def test_hyphenated_project_is_backtick_quoted() -> None:
    sql = _compile(load_domain(FIXTURES_DIR / "commerce.yaml")).sql
    assert "`my-project.semantic.commerce_graph`" in sql
    assert "`my-project.semantic._ontobq_commerce_n_customer`" in sql


def test_recompile_is_byte_for_byte_stable() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    views = compile_mapping_views(domain)
    first = compile_property_graph(domain, views)
    second = compile_property_graph(domain, views)
    assert first.sql == second.sql
    assert first.dependencies == second.dependencies


def test_dependencies_are_emitted_views_in_ir_order() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    views = compile_mapping_views(domain)
    extra = MappingViewArtifact(
        kind="entity",
        semantic_name="Unused",
        view_name="unused",
        qualified_name="my-project.semantic.unused",
        sql="-- unused",
        source="my-project.raw.unused",
        output_columns=("id",),
    )
    artifact = compile_property_graph(domain, (*views, extra))
    assert artifact.dependencies == tuple(item.qualified_name for item in views)
    assert extra.qualified_name not in artifact.dependencies
    assert artifact.sql == _golden("commerce.sql")


def test_compiler_consumes_mapping_view_artifacts_not_naming_helpers() -> None:
    module_file = property_graph_module.__file__
    assert module_file is not None
    text = Path(module_file).read_text(encoding="utf-8")
    assert "node_view_name" not in text
    assert "edge_view_name" not in text
    assert "def normalize_view_segment" not in text
    assert re.search(r"\.mapping\b", text) is None
    assert "column:" not in text
    assert "expression:" not in text
    assert "_ontobq_" not in text


def test_compiler_performs_no_io_and_imports_no_bigquery_client() -> None:
    _compile(load_domain(FIXTURES_DIR / "commerce.yaml"))
    module_file = property_graph_module.__file__
    assert module_file is not None
    text = Path(module_file).read_text(encoding="utf-8")
    assert "google.cloud" not in text
    assert "from google" not in text
    assert "open(" not in text
    assert "Path(" not in text
    assert not any("google.cloud.bigquery" in name for name in sys.modules)
    assert "google.cloud" not in sys.modules


def test_missing_entity_artifact_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    views = tuple(
        item for item in compile_mapping_views(domain) if item.semantic_name != "Customer"
    )
    with pytest.raises(ValueError, match="missing entity mapping-view artifact for 'Customer'"):
        compile_property_graph(domain, views)


def test_missing_relationship_artifact_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    views = tuple(item for item in compile_mapping_views(domain) if item.semantic_name != "PLACED")
    with pytest.raises(ValueError, match="missing relationship mapping-view artifact for 'PLACED'"):
        compile_property_graph(domain, views)


def test_missing_graph_name_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    broken = Domain(
        api_version=domain.api_version,
        kind=domain.kind,
        metadata=domain.metadata,
        bigquery=BigQueryTarget(
            project=domain.bigquery.project,
            dataset=domain.bigquery.dataset,
            graph="",
        ),
        entities=domain.entities,
        relationships=domain.relationships,
    )
    with pytest.raises(ValueError, match=r"missing spec\.bigquery\.graph"):
        compile_property_graph(broken, compile_mapping_views(domain))


def test_dotted_graph_name_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    broken = _with_graph(domain, "sales.graph")
    with pytest.raises(
        ValueError,
        match=r"invalid spec\.bigquery\.graph 'sales\.graph': "
        r"must be one BigQuery identifier component",
    ):
        compile_property_graph(broken, compile_mapping_views(domain))


def test_invalid_graph_name_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    broken = _with_graph(domain, "sales-graph")
    with pytest.raises(
        ValueError,
        match=r"invalid spec\.bigquery\.graph 'sales-graph': "
        r"must be one BigQuery identifier component",
    ):
        compile_property_graph(broken, compile_mapping_views(domain))


def test_duplicate_node_key_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    broken = _with_customer_key(domain, ("id", "id"))
    with pytest.raises(ValueError, match="duplicate key 'id' on entity 'Customer'"):
        compile_property_graph(broken, compile_mapping_views(domain))


def test_undeclared_node_key_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    broken = _with_customer_key(domain, ("ghost",))
    with pytest.raises(ValueError, match="undeclared key 'ghost' on entity 'Customer'"):
        compile_property_graph(broken, compile_mapping_views(domain))


def test_unknown_endpoint_entity_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    views = compile_mapping_views(domain)
    placed = domain.relationships["PLACED"]
    broken = RelationshipDefinition(
        from_entity="Missing",
        to_entity=placed.to_entity,
        mapping=placed.mapping,
        properties=placed.properties,
    )
    broken_domain = Domain(
        api_version=domain.api_version,
        kind=domain.kind,
        metadata=domain.metadata,
        bigquery=domain.bigquery,
        entities=domain.entities,
        relationships={"PLACED": broken},
    )
    with pytest.raises(ValueError, match="unknown entity 'Missing'"):
        compile_property_graph(broken_domain, views)


def test_hyphenated_semantic_name_is_quoted() -> None:
    entity = EntityDefinition(
        key=("id",),
        properties={"id": PropertyDefinition(type=PropertyType.STRING, nullable=False)},
        mapping=BigQueryEntityMapping(
            source="my-project.raw.customers",
            properties={"id": ColumnMapping(column="customer_id")},
        ),
    )
    domain = Domain(
        api_version="ontobq.dev/v1alpha1",
        kind="Domain",
        metadata=Metadata(name="commerce"),
        bigquery=BigQueryTarget(project="my-project", dataset="semantic", graph="commerce_graph"),
        entities={"Bad-Name": entity},
        relationships={},
    )
    sql = _compile(domain).sql
    assert "AS `Bad-Name`" in sql
    assert "LABEL `Bad-Name`" in sql


def _with_graph(domain: Domain, graph: str) -> Domain:
    return Domain(
        api_version=domain.api_version,
        kind=domain.kind,
        metadata=domain.metadata,
        bigquery=BigQueryTarget(
            project=domain.bigquery.project,
            dataset=domain.bigquery.dataset,
            graph=graph,
        ),
        entities=domain.entities,
        relationships=domain.relationships,
    )


def _with_customer_key(domain: Domain, key: tuple[str, ...]) -> Domain:
    customer = domain.entities["Customer"]
    entity = EntityDefinition(
        key=key,
        properties=customer.properties,
        mapping=customer.mapping,
        description=customer.description,
    )
    return Domain(
        api_version=domain.api_version,
        kind=domain.kind,
        metadata=domain.metadata,
        bigquery=domain.bigquery,
        entities={**domain.entities, "Customer": entity},
        relationships=domain.relationships,
    )


def _artifact(views: tuple[MappingViewArtifact, ...], name: str) -> MappingViewArtifact:
    for item in views:
        if item.semantic_name == name:
            return item
    raise AssertionError(f"missing artifact {name!r}")


def _line_item_domain() -> Domain:
    order = EntityDefinition(
        key=("id",),
        properties={"id": PropertyDefinition(type=PropertyType.STRING, nullable=False)},
        mapping=BigQueryEntityMapping(
            source="my-project.raw.orders",
            properties={"id": ColumnMapping(column="order_id")},
        ),
    )
    line_item = EntityDefinition(
        key=("orderId", "sku"),
        properties={
            "orderId": PropertyDefinition(type=PropertyType.STRING, nullable=False),
            "sku": PropertyDefinition(type=PropertyType.STRING, nullable=False),
            "quantity": PropertyDefinition(type=PropertyType.INTEGER),
        },
        mapping=BigQueryEntityMapping(
            source="my-project.raw.order_items",
            properties={
                "orderId": ColumnMapping(column="order_id"),
                "sku": ColumnMapping(column="sku"),
                "quantity": ColumnMapping(column="qty"),
            },
        ),
    )
    contains = RelationshipDefinition(
        from_entity="Order",
        to_entity="LineItem",
        mapping=BigQueryRelationshipMapping(
            source="my-project.raw.order_items",
            key=(ColumnMapping(column="order_id"), ColumnMapping(column="sku")),
            from_endpoint={"id": ColumnMapping(column="order_id")},
            to_endpoint={
                "orderId": ColumnMapping(column="order_id"),
                "sku": ColumnMapping(column="sku"),
            },
            properties={},
        ),
        properties={},
    )
    return Domain(
        api_version="ontobq.dev/v1alpha1",
        kind="Domain",
        metadata=Metadata(name="commerce"),
        bigquery=BigQueryTarget(project="my-project", dataset="semantic", graph="commerce_graph"),
        entities={"Order": order, "LineItem": line_item},
        relationships={"CONTAINS": contains},
    )
