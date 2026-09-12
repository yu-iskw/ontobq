"""Integrity SQL compiler tests against Domain IR fixtures and in-memory IR."""

from __future__ import annotations

import re
import sys
from pathlib import Path

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
    compile_integrity_queries,
    compile_mapping_views,
    load_domain,
    sql as sql_package,
)
from ontobq.compile import mapping_views as mapping_views_module
from ontobq.sql import interpolate as interpolate_module
from ontobq.tests.paths import FIXTURES_DIR, TESTS_DIR
from ontobq.validate import IntegrityQuery, integrity as integrity_module
from ontobq.validate.integrity import DEFAULT_EVIDENCE_LIMIT

_GOLDENS = TESTS_DIR / "goldens" / "integrity"
_FROM_RESOURCE = re.compile(r"FROM `([^`]+)`")
_DDL_DML = (
    "CREATE ",
    "DROP ",
    "INSERT ",
    "UPDATE ",
    "DELETE ",
    "MERGE ",
    "TRUNCATE ",
    "ALTER ",
    "TABLESAMPLE",
    "PROPERTY GRAPH",
    "RAND(",
)


def _golden(name: str) -> str:
    return (_GOLDENS / name).read_text(encoding="utf-8")


def _by_code(queries: tuple[IntegrityQuery, ...], code: str, element: str) -> IntegrityQuery:
    for query in queries:
        if query.code == code and query.element == element:
            return query
    raise AssertionError(f"missing {code} for {element!r}")


def _sources(domain: Domain) -> set[str]:
    found = {entity.mapping.source for entity in domain.entities.values()}
    found.update(rel.mapping.source for rel in domain.relationships.values())
    return found


def test_commerce_query_order_and_paths() -> None:
    queries = compile_integrity_queries(load_domain(FIXTURES_DIR / "commerce.yaml"))
    assert [(item.code, item.element) for item in queries] == [
        ("OBQ201", "Customer"),
        ("OBQ202", "Customer"),
        ("OBQ201", "Order"),
        ("OBQ202", "Order"),
        ("OBQ203", "PLACED"),
        ("OBQ204", "PLACED"),
        ("OBQ205", "PLACED"),
        ("OBQ206", "PLACED"),
    ]
    customer = _by_code(queries, "OBQ201", "Customer")
    assert customer.path == "spec.entities.Customer.key"
    assert customer.evidence_limit == DEFAULT_EVIDENCE_LIMIT
    placed_key = _by_code(queries, "OBQ203", "PLACED")
    assert placed_key.path == "spec.relationships.PLACED.mapping.bigquery.key"
    assert _by_code(queries, "OBQ205", "PLACED").path == (
        "spec.relationships.PLACED.mapping.bigquery.from"
    )
    assert _by_code(queries, "OBQ206", "PLACED").path == (
        "spec.relationships.PLACED.mapping.bigquery.to"
    )


def test_commerce_customer_obq201_202_golden() -> None:
    queries = compile_integrity_queries(load_domain(FIXTURES_DIR / "commerce.yaml"))
    obq201 = _by_code(queries, "OBQ201", "Customer")
    obq202 = _by_code(queries, "OBQ202", "Customer")
    assert "customer_id AS id" in obq201.sql
    assert "`my-project.raw.customers`" in obq201.sql
    assert obq201.sql == _golden("commerce_customer_obq201.sql")
    assert obq202.sql == _golden("commerce_customer_obq202.sql")


def test_commerce_placed_obq203_204_golden() -> None:
    queries = compile_integrity_queries(load_domain(FIXTURES_DIR / "commerce.yaml"))
    obq203 = _by_code(queries, "OBQ203", "PLACED")
    obq204 = _by_code(queries, "OBQ204", "PLACED")
    assert "order_id AS key_0" in obq203.sql
    assert "`my-project.raw.orders`" in obq203.sql
    assert obq203.sql == _golden("commerce_placed_obq203.sql")
    assert obq204.sql == _golden("commerce_placed_obq204.sql")


def test_commerce_placed_obq205_golden() -> None:
    sql = _by_code(
        compile_integrity_queries(load_domain(FIXTURES_DIR / "commerce.yaml")),
        "OBQ205",
        "PLACED",
    ).sql
    assert "customer_id AS id" in sql
    assert "`my-project.raw.orders`" in sql
    assert "`my-project.raw.customers`" in sql
    assert "ON edge.id = node.id" in sql
    assert sql == _golden("commerce_placed_obq205.sql")


def test_commerce_placed_obq206_golden() -> None:
    sql = _by_code(
        compile_integrity_queries(load_domain(FIXTURES_DIR / "commerce.yaml")),
        "OBQ206",
        "PLACED",
    ).sql
    assert "order_id AS id" in sql
    assert _FROM_RESOURCE.findall(sql) == [
        "my-project.raw.orders",
        "my-project.raw.orders",
    ]
    assert sql == _golden("commerce_placed_obq206.sql")


def _expression_key_domain() -> Domain:
    entity = EntityDefinition(
        key=("createdAt",),
        properties={"createdAt": PropertyDefinition(type=PropertyType.TIMESTAMP, nullable=False)},
        mapping=BigQueryEntityMapping(
            source="my-project.raw.orders",
            properties={"createdAt": ExpressionMapping(expression="TIMESTAMP(created_at)")},
        ),
    )
    return Domain(
        api_version="ontobq.dev/v1alpha1",
        kind="Domain",
        metadata=Metadata(name="commerce"),
        bigquery=BigQueryTarget(project="my-project", dataset="semantic", graph="commerce_graph"),
        entities={"Order": entity},
        relationships={},
    )


def test_expression_mapping_key_is_verbatim() -> None:
    queries = compile_integrity_queries(_expression_key_domain())
    sql = _by_code(queries, "OBQ201", "Order").sql
    assert "TIMESTAMP(created_at) AS createdAt" in sql
    assert "AS created_at" not in sql
    assert sql == _golden("expression_order_obq201.sql")


def test_composite_entity_key_null_or_and_unique_and() -> None:
    queries = compile_integrity_queries(load_domain(FIXTURES_DIR / "composite-key.yaml"))
    obq201 = _by_code(queries, "OBQ201", "Customer")
    obq202 = _by_code(queries, "OBQ202", "Customer")
    assert "tenant_id AS tenantId" in obq201.sql
    assert "customer_id AS id" in obq201.sql
    assert "projected.tenantId IS NULL OR projected.id IS NULL" in obq201.sql
    assert "projected.tenantId IS NOT NULL AND projected.id IS NOT NULL" in obq202.sql
    assert obq201.sql == _golden("composite_customer_obq201.sql")
    assert obq202.sql == _golden("composite_customer_obq202.sql")


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


def test_composite_endpoint_join_ands_every_key_component() -> None:
    sql = _by_code(compile_integrity_queries(_line_item_domain()), "OBQ206", "CONTAINS").sql
    assert "ON edge.orderId = node.orderId AND edge.sku = node.sku" in sql
    assert "order_id AS orderId" in sql
    assert sql == _golden("composite_contains_obq206.sql")


def test_generated_sql_is_read_only_source_scans() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    allowed = _sources(domain)
    for query in compile_integrity_queries(domain):
        sql = query.sql
        assert "SELECT *" not in sql
        assert "_ontobq_" not in sql
        assert "__ontobq_" not in sql
        upper = sql.upper()
        for token in _DDL_DML:
            assert token not in upper
        assert set(_FROM_RESOURCE.findall(sql)) <= allowed


def test_recompile_is_byte_for_byte_stable() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    first = compile_integrity_queries(domain)
    second = compile_integrity_queries(domain)
    assert [item.sql for item in first] == [item.sql for item in second]
    assert [(item.code, item.element) for item in first] == [
        (item.code, item.element) for item in second
    ]


def test_evidence_limit_is_baked_into_outer_limit() -> None:
    limit = 7
    sql = compile_integrity_queries(
        load_domain(FIXTURES_DIR / "commerce.yaml"), evidence_limit=limit
    )[0].sql
    assert sql.endswith(f"LIMIT {limit}\n")
    assert f"LIMIT {limit}" in sql.split("ORDER BY")[-1]


def test_invalid_evidence_limit_is_rejected() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    with pytest.raises(ValueError, match="evidence_limit"):
        compile_integrity_queries(domain, evidence_limit=0)


def _with_entities(domain: Domain, entities: dict[str, EntityDefinition]) -> Domain:
    return Domain(
        api_version=domain.api_version,
        kind=domain.kind,
        metadata=domain.metadata,
        bigquery=domain.bigquery,
        entities=entities,
        relationships=domain.relationships,
    )


def test_empty_entity_key_is_rejected() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    customer = domain.entities["Customer"]
    broken = EntityDefinition(key=(), properties=customer.properties, mapping=customer.mapping)
    with pytest.raises(ValueError, match="must not be empty"):
        compile_integrity_queries(_with_entities(domain, {"Customer": broken}))


def _with_relationships(domain: Domain, relationships: dict[str, RelationshipDefinition]) -> Domain:
    return Domain(
        api_version=domain.api_version,
        kind=domain.kind,
        metadata=domain.metadata,
        bigquery=domain.bigquery,
        entities=domain.entities,
        relationships=relationships,
    )


def test_empty_relationship_key_is_rejected() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    placed = domain.relationships["PLACED"]
    mapping = placed.mapping
    broken = RelationshipDefinition(
        from_entity=placed.from_entity,
        to_entity=placed.to_entity,
        mapping=BigQueryRelationshipMapping(
            source=mapping.source,
            key=(),
            from_endpoint=mapping.from_endpoint,
            to_endpoint=mapping.to_endpoint,
            properties=mapping.properties,
        ),
        properties=placed.properties,
    )
    with pytest.raises(ValueError, match="must not be empty"):
        compile_integrity_queries(_with_relationships(domain, {"PLACED": broken}))


def test_unknown_relationship_endpoint_entity_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    placed = domain.relationships["PLACED"]
    broken = RelationshipDefinition(
        from_entity="Missing",
        to_entity=placed.to_entity,
        mapping=placed.mapping,
        properties=placed.properties,
    )
    with pytest.raises(ValueError, match="unknown entity 'Missing'"):
        compile_integrity_queries(_with_relationships(domain, {"PLACED": broken}))


def test_missing_entity_key_mapping_raises() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    customer = domain.entities["Customer"]
    broken = EntityDefinition(
        key=customer.key,
        properties=customer.properties,
        mapping=BigQueryEntityMapping(source=customer.mapping.source, properties={}),
    )
    with pytest.raises(ValueError, match="missing entity key mapping"):
        compile_integrity_queries(_with_entities(domain, {"Customer": broken}))


def test_compiler_and_interpolator_import_no_bigquery_or_mapping_views() -> None:
    compile_integrity_queries(load_domain(FIXTURES_DIR / "commerce.yaml"))
    for module in (integrity_module, interpolate_module, sql_package):
        module_file = module.__file__
        assert module_file is not None
        text = Path(module_file).read_text(encoding="utf-8")
        assert "google.cloud" not in text
        assert "from google" not in text
        assert "from ontobq.compile" not in text
        assert "import compile_mapping_views" not in text
    assert not any("google.cloud.bigquery" in name for name in sys.modules)
    assert "google.cloud" not in sys.modules


def test_mapping_views_use_shared_interpolator() -> None:
    module_file = mapping_views_module.__file__
    assert module_file is not None
    text = Path(module_file).read_text(encoding="utf-8")
    assert "from ontobq.sql.interpolate import" in text
    view_sql = compile_mapping_views(load_domain(FIXTURES_DIR / "commerce.yaml"))[0].sql
    integrity_sql = compile_integrity_queries(load_domain(FIXTURES_DIR / "commerce.yaml"))[0].sql
    assert "`my-project.raw.customers`" in view_sql
    assert "`my-project.raw.customers`" in integrity_sql


def test_expression_mapping_fixture_key_still_uses_column() -> None:
    sql = _by_code(
        compile_integrity_queries(load_domain(FIXTURES_DIR / "expression-mapping.yaml")),
        "OBQ201",
        "Order",
    ).sql
    assert "order_id AS id" in sql


def _entity_only_domain(name: str, entity: EntityDefinition) -> Domain:
    return Domain(
        api_version="ontobq.dev/v1alpha1",
        kind="Domain",
        metadata=Metadata(name="commerce"),
        bigquery=BigQueryTarget(project="my-project", dataset="semantic", graph="commerce_graph"),
        entities={name: entity},
        relationships={},
    )


def test_reserved_alias_and_source_column_are_backticked() -> None:
    entity = EntityDefinition(
        key=("SELECT",),
        properties={"SELECT": PropertyDefinition(type=PropertyType.STRING, nullable=False)},
        mapping=BigQueryEntityMapping(
            source="my-project.raw.customers",
            properties={"SELECT": ColumnMapping(column="FROM")},
        ),
    )
    sql = _by_code(
        compile_integrity_queries(_entity_only_domain("Customer", entity)),
        "OBQ201",
        "Customer",
    ).sql
    assert "`FROM` AS `SELECT`" in sql
    assert "projected.`SELECT` IS NULL" in sql
    assert "GROUP BY\n  projected.`SELECT`" in sql
    assert "ORDER BY\n  violation_count DESC,\n  projected.`SELECT`" in sql


def test_reserved_source_column_with_safe_alias_is_backticked() -> None:
    entity = EntityDefinition(
        key=("id",),
        properties={"id": PropertyDefinition(type=PropertyType.STRING, nullable=False)},
        mapping=BigQueryEntityMapping(
            source="my-project.raw.customers",
            properties={"id": ColumnMapping(column="FROM")},
        ),
    )
    sql = _by_code(
        compile_integrity_queries(_entity_only_domain("Customer", entity)),
        "OBQ202",
        "Customer",
    ).sql
    assert "`FROM` AS id" in sql
    assert "projected.id IS NOT NULL" in sql


def _typed_key_entity(prop_type: PropertyType, column: str, alias: str) -> EntityDefinition:
    return EntityDefinition(
        key=(alias,),
        properties={alias: PropertyDefinition(type=prop_type, nullable=False)},
        mapping=BigQueryEntityMapping(
            source="my-project.raw.documents",
            properties={alias: ColumnMapping(column=column)},
        ),
    )


def test_json_entity_key_uses_to_json_string() -> None:
    entity = _typed_key_entity(PropertyType.JSON, "payload", "payload")
    domain = _entity_only_domain("Document", entity)
    sql = _by_code(compile_integrity_queries(domain), "OBQ202", "Document").sql
    assert "TO_JSON_STRING(payload) AS payload" in sql
    assert "GROUP BY\n  projected.payload" in sql
    assert "ORDER BY\n  violation_count DESC,\n  projected.payload" in sql


def test_geography_entity_key_uses_st_asgeojson() -> None:
    domain = _entity_only_domain("Place", _typed_key_entity(PropertyType.GEOGRAPHY, "geom", "geom"))
    sql = _by_code(compile_integrity_queries(domain), "OBQ201", "Place").sql
    assert "ST_ASGEOJSON(geom) AS geom" in sql
    assert "projected.geom IS NULL" in sql
    assert "GROUP BY\n  projected.geom" in sql


def test_json_orphan_check_wraps_edge_and_node_keys() -> None:
    document = _typed_key_entity(PropertyType.JSON, "payload", "payload")
    cites = RelationshipDefinition(
        from_entity="Document",
        to_entity="Document",
        mapping=BigQueryRelationshipMapping(
            source="my-project.raw.citations",
            key=(ColumnMapping(column="cite_id"),),
            from_endpoint={"payload": ColumnMapping(column="from_payload")},
            to_endpoint={"payload": ColumnMapping(column="to_payload")},
            properties={},
        ),
        properties={},
    )
    domain = Domain(
        api_version="ontobq.dev/v1alpha1",
        kind="Domain",
        metadata=Metadata(name="commerce"),
        bigquery=BigQueryTarget(project="my-project", dataset="semantic", graph="commerce_graph"),
        entities={"Document": document},
        relationships={"CITES": cites},
    )
    sql = _by_code(compile_integrity_queries(domain), "OBQ205", "CITES").sql
    assert "TO_JSON_STRING(from_payload) AS payload" in sql
    assert "TO_JSON_STRING(payload) AS payload" in sql
    assert "ON edge.payload = node.payload" in sql
