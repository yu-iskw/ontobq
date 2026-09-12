"""Loader tests: YAML/JSON parse, structural validation, typed Domain IR."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest  # pyright: ignore[reportMissingImports]

from ontobq import ColumnMapping, Domain, DomainLoadError, ExpressionMapping, load_domain
from ontobq.tests.paths import EXAMPLES_DIR, FIXTURES_DIR

if TYPE_CHECKING:
    from pathlib import Path


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


def _assert_obq000(path: Path) -> DomainLoadError:
    with pytest.raises(DomainLoadError, match="OBQ000") as caught:
        load_domain(path)
    return caught.value


def _diagnostics_text(error: DomainLoadError) -> str:
    return " ".join(f"{item.path} {item.message}" for item in error.diagnostics)


def _duplicate_customer_entity_yaml(source: str) -> str:
    return (
        "    Customer:\n"
        "      key: [id]\n"
        "      properties:\n"
        "        id:\n"
        "          type: string\n"
        "      mapping:\n"
        "        bigquery:\n"
        f"          source: {source}\n"
        "          properties:\n"
        "            id:\n"
        "              column: customer_id\n"
    )


def _duplicate_customer_domain_yaml() -> str:
    first = _duplicate_customer_entity_yaml("my-project.raw.customers_a")
    second = _duplicate_customer_entity_yaml("my-project.raw.customers_b")
    return (
        "apiVersion: ontobq.dev/v1alpha1\n"
        "kind: Domain\n"
        "metadata:\n"
        "  name: commerce\n"
        "spec:\n"
        "  bigquery:\n"
        "    project: my-project\n"
        "    dataset: semantic\n"
        "    graph: commerce_graph\n"
        "  entities:\n"
        f"{first}"
        f"{second}"
    )


def _duplicate_customer_entity_json(source: str) -> str:
    return (
        '"Customer":{'
        '"key":["id"],'
        '"properties":{"id":{"type":"string"}},'
        '"mapping":{"bigquery":{'
        f'"source":"{source}",'
        '"properties":{"id":{"column":"customer_id"}}'
        "}}"
        "}"
    )


def _duplicate_customer_domain_json() -> str:
    first = _duplicate_customer_entity_json("my-project.raw.customers_a")
    second = _duplicate_customer_entity_json("my-project.raw.customers_b")
    return (
        "{"
        '"apiVersion":"ontobq.dev/v1alpha1",'
        '"kind":"Domain",'
        '"metadata":{"name":"commerce"},'
        '"spec":{'
        '"bigquery":{"project":"my-project","dataset":"semantic","graph":"commerce_graph"},'
        '"entities":{'
        f"{first},{second}"
        "}"
        "}"
        "}"
    )


def test_load_domain_missing_file_raises_obq000(tmp_path: Path) -> None:
    missing = tmp_path / "missing-domain.yaml"
    error = _assert_obq000(missing)
    assert "does not exist" in _diagnostics_text(error)


def test_load_domain_unsupported_suffix_raises_obq000(tmp_path: Path) -> None:
    path = tmp_path / "domain.txt"
    path.write_text("apiVersion: ontobq.dev/v1alpha1\n", encoding="utf-8")
    error = _assert_obq000(path)
    joined = _diagnostics_text(error)
    assert ".txt" in joined
    assert "yaml" in joined.lower() or "json" in joined.lower()


def test_load_domain_malformed_json_raises_obq000(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    error = _assert_obq000(path)
    assert "invalid JSON" in _diagnostics_text(error)


def test_load_domain_malformed_yaml_raises_obq000(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text(":\n  - [", encoding="utf-8")
    error = _assert_obq000(path)
    assert "invalid YAML" in _diagnostics_text(error)


def test_load_domain_duplicate_entity_keys_yaml_raises_obq000(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-entities.yaml"
    path.write_text(_duplicate_customer_domain_yaml(), encoding="utf-8")
    error = _assert_obq000(path)
    joined = _diagnostics_text(error)
    assert "Customer" in joined
    assert "entities" in joined


def test_load_domain_duplicate_entity_keys_json_raises_obq000(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-entities.json"
    path.write_text(_duplicate_customer_domain_json(), encoding="utf-8")
    error = _assert_obq000(path)
    joined = _diagnostics_text(error)
    assert "Customer" in joined
    assert "entities" in joined


def test_load_domain_date_like_yaml_key_raises_obq000() -> None:
    error = _assert_obq000(FIXTURES_DIR / "invalid-date-key.yaml")
    assert any("2024-01-01" in item.path for item in error.diagnostics)


def test_load_domain_invalid_utf8_raises_obq000(tmp_path: Path) -> None:
    path = tmp_path / "invalid-utf8.yaml"
    path.write_bytes(b"\xff\xfe")
    error = _assert_obq000(path)
    assert error.__cause__ is not None
    assert isinstance(error.__cause__, UnicodeError)


def _file_is_readable(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
    except OSError:
        return False
    return True


def _assert_unreadable_domain(path: Path) -> None:
    if _file_is_readable(path):
        pytest.skip("filesystem still allows reading after chmod 000")
    error = _assert_obq000(path)
    assert error.__cause__ is not None
    assert isinstance(error.__cause__, OSError)


def test_load_domain_unreadable_file_raises_obq000(tmp_path: Path) -> None:
    path = tmp_path / "unreadable.yaml"
    path.write_text("apiVersion: ontobq.dev/v1alpha1\n", encoding="utf-8")
    path.chmod(0o000)
    try:
        _assert_unreadable_domain(path)
    finally:
        path.chmod(0o644)
