"""View naming helper freeze for mapping-view compilers."""

from __future__ import annotations

from ontobq import (
    edge_key_column,
    edge_view_name,
    from_key_column,
    node_view_name,
    normalize_view_segment,
    to_key_column,
)


def test_naming_node_view_customer() -> None:
    assert node_view_name("commerce", "Customer") == "_ontobq_commerce_n_customer"


def test_naming_edge_view_placed() -> None:
    assert edge_view_name("commerce", "PLACED") == "_ontobq_commerce_e_placed"


def test_naming_helper_columns() -> None:
    assert edge_key_column(0) == "__ontobq_edge_key_0"
    assert from_key_column("id") == "__ontobq_from_id"
    assert to_key_column("id") == "__ontobq_to_id"


def test_naming_case_normalization() -> None:
    assert normalize_view_segment("Customer") == "customer"
    assert node_view_name("Commerce", "CUSTOMER") == "_ontobq_commerce_n_customer"
