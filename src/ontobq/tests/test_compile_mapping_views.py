"""Mapping-view SQL compiler tests against Domain IR fixtures and in-memory IR."""

from __future__ import annotations

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
    ExpressionMapping,
    Metadata,
    PropertyDefinition,
    PropertyType,
    RelationshipDefinition,
    compile_mapping_views,
    edge_view_name,
    load_domain,
    node_view_name,
)
from ontobq.compile import mapping_views as mapping_views_module
from ontobq.tests.paths import FIXTURES_DIR, TESTS_DIR

if TYPE_CHECKING:
    from ontobq.compile.mapping_views import MappingViewArtifact

_GOLDENS = TESTS_DIR / "goldens" / "mapping_views"


def _golden(name: str) -> str:
    return (_GOLDENS / name).read_text(encoding="utf-8")


def _by_name(artifacts: tuple[MappingViewArtifact, ...], name: str) -> MappingViewArtifact:
    for artifact in artifacts:
        if artifact.semantic_name == name:
            return artifact
    raise AssertionError(f"missing artifact {name!r}")


def _sql_texts(artifacts: tuple[MappingViewArtifact, ...]) -> list[str]:
    return [artifact.sql for artifact in artifacts]


def test_commerce_emits_one_artifact_per_entity_and_relationship() -> None:
    artifacts = compile_mapping_views(load_domain(FIXTURES_DIR / "commerce.yaml"))
    assert [item.kind for item in artifacts] == ["entity", "entity", "relationship"]
    assert [item.semantic_name for item in artifacts] == ["Customer", "Order", "PLACED"]


def test_commerce_customer_node_view_golden() -> None:
    artifacts = compile_mapping_views(load_domain(FIXTURES_DIR / "commerce.yaml"))
    customer = _by_name(artifacts, "Customer")
    assert customer.view_name == node_view_name("commerce", "Customer")
    assert customer.qualified_name == "my-project.semantic._ontobq_commerce_n_customer"
    assert customer.source == "my-project.raw.customers"
    assert customer.output_columns == ("id", "name", "country")
    assert customer.edge_key_columns == ()
    assert customer.sql == _golden("commerce_n_customer.sql")


def test_commerce_order_node_view_golden() -> None:
    artifacts = compile_mapping_views(load_domain(FIXTURES_DIR / "commerce.yaml"))
    order = _by_name(artifacts, "Order")
    assert order.view_name == "_ontobq_commerce_n_order"
    assert order.output_columns == ("id", "createdAt", "status")
    assert order.sql == _golden("commerce_n_order.sql")


def test_commerce_placed_edge_view_golden() -> None:
    artifacts = compile_mapping_views(load_domain(FIXTURES_DIR / "commerce.yaml"))
    placed = _by_name(artifacts, "PLACED")
    assert placed.kind == "relationship"
    assert placed.view_name == edge_view_name("commerce", "PLACED")
    assert placed.edge_key_columns == ("__ontobq_edge_key_0",)
    assert placed.from_columns == ("__ontobq_from_id",)
    assert placed.to_columns == ("__ontobq_to_id",)
    assert placed.output_columns == (
        "__ontobq_edge_key_0",
        "__ontobq_from_id",
        "__ontobq_to_id",
        "placedAt",
    )
    assert "AS created_at" not in placed.sql
    assert "AS placedAt" in placed.sql
    assert placed.sql == _golden("commerce_e_placed.sql")


def test_expression_mapping_fixture_golden() -> None:
    artifacts = compile_mapping_views(load_domain(FIXTURES_DIR / "expression-mapping.yaml"))
    order = _by_name(artifacts, "Order")
    assert "TIMESTAMP(created_at) AS createdAt" in order.sql
    assert "AS created_at" not in order.sql
    assert order.sql == _golden("expression_n_order.sql")


def test_trim_expression_uses_semantic_alias() -> None:
    artifacts = compile_mapping_views(_trim_customer_domain())
    customer = _by_name(artifacts, "Customer")
    assert customer.sql == _golden("expression_n_customer.sql")
    assert "AS customer_name" not in customer.sql


def test_composite_node_key_has_no_helper_columns() -> None:
    artifacts = compile_mapping_views(load_domain(FIXTURES_DIR / "composite-key.yaml"))
    customer = _by_name(artifacts, "Customer")
    assert customer.output_columns == ("tenantId", "id")
    assert "__ontobq_" not in customer.sql
    assert customer.sql == _golden("composite_n_customer.sql")


def test_composite_edge_and_endpoint_keys() -> None:
    artifacts = compile_mapping_views(_line_item_domain())
    line_item = _by_name(artifacts, "LineItem")
    contains = _by_name(artifacts, "CONTAINS")
    assert line_item.sql == _golden("composite_n_lineitem.sql")
    assert "__ontobq_" not in line_item.sql
    assert contains.edge_key_columns == ("__ontobq_edge_key_0", "__ontobq_edge_key_1")
    assert contains.from_columns == ("__ontobq_from_id",)
    assert contains.to_columns == ("__ontobq_to_orderId", "__ontobq_to_sku")
    assert contains.sql == _golden("composite_e_contains.sql")


def test_hyphenated_project_is_backtick_quoted() -> None:
    artifacts = compile_mapping_views(load_domain(FIXTURES_DIR / "commerce.yaml"))
    customer = _by_name(artifacts, "Customer")
    assert "`my-project.semantic._ontobq_commerce_n_customer`" in customer.sql
    assert "`my-project.raw.customers`" in customer.sql


def test_non_three_part_source_is_quoted_as_one_name() -> None:
    artifacts = compile_mapping_views(_source_domain("raw.customers"))
    assert "FROM `raw.customers`;" in artifacts[0].sql


def test_unsafe_column_identifier_is_quoted() -> None:
    artifacts = compile_mapping_views(_column_domain("customer-id"))
    assert "`customer-id` AS id" in artifacts[0].sql


def test_top_level_comma_expression_is_rejected() -> None:
    with pytest.raises(ValueError, match="scalar GoogleSQL"):
        compile_mapping_views(_expression_domain("foo, bar"))


def test_top_level_as_expression_is_rejected() -> None:
    with pytest.raises(ValueError, match="scalar GoogleSQL"):
        compile_mapping_views(_expression_domain("x AS y"))


def test_scalar_expressions_compile_verbatim() -> None:
    casted = compile_mapping_views(_expression_domain("CAST(x AS STRING)"))[0]
    concat = compile_mapping_views(_expression_domain("CONCAT(a, b)"))[0]
    quoted = compile_mapping_views(_expression_domain("'a, b'"))[0]
    doubled = compile_mapping_views(_expression_domain("'a''b'"))[0]
    escaped = compile_mapping_views(_expression_domain(r"'a\,b'"))[0]
    extra_paren = compile_mapping_views(_expression_domain("id)"))[0]
    unclosed = compile_mapping_views(_expression_domain("'still-open"))[0]
    assert "CAST(x AS STRING) AS id" in casted.sql
    assert "CONCAT(a, b) AS id" in concat.sql
    assert "'a, b' AS id" in quoted.sql
    assert "'a''b' AS id" in doubled.sql
    assert r"'a\,b' AS id" in escaped.sql
    assert "id) AS id" in extra_paren.sql
    assert "'still-open AS id" in unclosed.sql


def test_line_comment_does_not_swallow_non_final_alias() -> None:
    domain = _two_property_domain(
        ExpressionMapping(expression="TRIM(name) -- trimmed"),
        ColumnMapping(column="country"),
    )
    sql = compile_mapping_views(domain)[0].sql
    assert "TRIM(name) -- trimmed\n  AS id," in sql
    assert "country AS country" in sql


def test_line_comment_does_not_swallow_final_alias() -> None:
    domain = _two_property_domain(
        ColumnMapping(column="customer_id"),
        ExpressionMapping(expression="country -- source"),
    )
    sql = compile_mapping_views(domain)[0].sql
    assert "customer_id AS id," in sql
    assert "country -- source\n  AS country" in sql
    assert "AS country\nFROM" in sql


def test_comma_or_as_inside_line_comment_is_still_scalar() -> None:
    comma = compile_mapping_views(_expression_domain("id -- x, y"))[0]
    as_kw = compile_mapping_views(_expression_domain("id -- AS x"))[0]
    quoted = compile_mapping_views(_expression_domain("'-- not comment'"))[0]
    assert "id -- x, y\n  AS id" in comma.sql
    assert "id -- AS x\n  AS id" in as_kw.sql
    assert "'-- not comment' AS id" in quoted.sql


def test_recompile_is_byte_for_byte_stable() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    first = compile_mapping_views(domain)
    second = compile_mapping_views(domain)
    assert _sql_texts(first) == _sql_texts(second)
    assert [item.semantic_name for item in first] == [item.semantic_name for item in second]


def test_output_contains_no_select_star() -> None:
    artifacts = compile_mapping_views(load_domain(FIXTURES_DIR / "commerce.yaml"))
    for artifact in artifacts:
        assert "SELECT *" not in artifact.sql
        assert "*" not in {part.strip().rstrip(",") for part in artifact.sql.splitlines()}


def test_compiler_performs_no_io_and_imports_no_bigquery_client() -> None:
    compile_mapping_views(_trim_customer_domain())
    module_file = mapping_views_module.__file__
    assert module_file is not None
    text = Path(module_file).read_text(encoding="utf-8")
    assert "google.cloud" not in text
    assert "from google" not in text
    assert "open(" not in text
    assert "Path(" not in text
    assert not any("google.cloud.bigquery" in name for name in sys.modules)
    assert "google.cloud" not in sys.modules


def test_missing_property_mapping_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    customer = domain.entities["Customer"]
    broken = EntityDefinition(
        key=customer.key,
        properties=customer.properties,
        mapping=BigQueryEntityMapping(
            source=customer.mapping.source,
            properties={"id": customer.mapping.properties["id"]},
        ),
    )
    with pytest.raises(ValueError, match="missing entity property mapping for 'name'"):
        compile_mapping_views(_with_entities(domain, {"Customer": broken}))


def test_case_only_entity_view_collision_is_rejected() -> None:
    base = _id_entity_domain("Customer", "my-project.raw.customers", ColumnMapping(column="id"))
    entity = base.entities["Customer"]
    domain = _with_entities(base, {"Customer": entity, "customer": entity})
    with pytest.raises(ValueError, match="duplicate mapping view target") as caught:
        compile_mapping_views(domain)
    message = str(caught.value)
    assert "OBQ008" not in message
    assert "Customer" in message
    assert "customer" in message
    assert node_view_name(domain.metadata.name, "Customer") in message


def test_case_only_relationship_view_collision_is_rejected() -> None:
    base = _line_item_domain()
    contains = base.relationships["CONTAINS"]
    domain = Domain(
        api_version=base.api_version,
        kind=base.kind,
        metadata=base.metadata,
        bigquery=base.bigquery,
        entities=base.entities,
        relationships={"CONTAINS": contains, "contains": contains},
    )
    with pytest.raises(ValueError, match="duplicate mapping view target") as caught:
        compile_mapping_views(domain)
    message = str(caught.value)
    assert "OBQ008" not in message
    assert "CONTAINS" in message
    assert "contains" in message
    assert edge_view_name(domain.metadata.name, "CONTAINS") in message


def test_unknown_relationship_endpoint_entity_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
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
        compile_mapping_views(broken_domain)


def _with_entities(domain: Domain, entities: dict[str, EntityDefinition]) -> Domain:
    return Domain(
        api_version=domain.api_version,
        kind=domain.kind,
        metadata=domain.metadata,
        bigquery=domain.bigquery,
        entities=entities,
        relationships={},
    )


def _trim_customer_domain() -> Domain:
    return _entity_only_domain(
        "Customer",
        ("id",),
        {
            "id": PropertyDefinition(type=PropertyType.STRING, nullable=False),
            "name": PropertyDefinition(type=PropertyType.STRING),
            "country": PropertyDefinition(type=PropertyType.STRING),
        },
        "my-project.raw.customers",
        {
            "id": ColumnMapping(column="customer_id"),
            "name": ExpressionMapping(expression="TRIM(customer_name)"),
            "country": ColumnMapping(column="country"),
        },
    )


def _source_domain(source: str) -> Domain:
    return _id_entity_domain("Customer", source, ColumnMapping(column="customer_id"))


def _column_domain(column: str) -> Domain:
    return _id_entity_domain("Customer", "my-project.raw.customers", ColumnMapping(column=column))


def _expression_domain(expression: str) -> Domain:
    return _id_entity_domain(
        "Customer", "my-project.raw.customers", ExpressionMapping(expression=expression)
    )


def _two_property_domain(
    id_mapping: ColumnMapping | ExpressionMapping,
    country_mapping: ColumnMapping | ExpressionMapping,
) -> Domain:
    return _entity_only_domain(
        "Customer",
        ("id",),
        {
            "id": PropertyDefinition(type=PropertyType.STRING, nullable=False),
            "country": PropertyDefinition(type=PropertyType.STRING),
        },
        "my-project.raw.customers",
        {"id": id_mapping, "country": country_mapping},
    )


def _id_entity_domain(name: str, source: str, mapping: ColumnMapping | ExpressionMapping) -> Domain:
    return _entity_only_domain(
        name,
        ("id",),
        {"id": PropertyDefinition(type=PropertyType.STRING, nullable=False)},
        source,
        {"id": mapping},
    )


def _entity_only_domain(
    name: str,
    key: tuple[str, ...],
    properties: dict[str, PropertyDefinition],
    source: str,
    mapped: dict[str, ColumnMapping | ExpressionMapping],
) -> Domain:
    entity = EntityDefinition(
        key=key,
        properties=properties,
        mapping=BigQueryEntityMapping(source=source, properties=mapped),
    )
    return Domain(
        api_version="ontobq.dev/v1alpha1",
        kind="Domain",
        metadata=Metadata(name="commerce"),
        bigquery=BigQueryTarget(project="my-project", dataset="semantic", graph="commerce_graph"),
        entities={name: entity},
        relationships={},
    )


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
