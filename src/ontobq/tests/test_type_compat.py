"""Explicit v1alpha1 semantic-to-physical type table."""

from __future__ import annotations

import pytest  # pyright: ignore[reportMissingImports]

from ontobq.ir import PropertyType
from ontobq.validate.type_compat import COMPATIBLE_PHYSICAL_TYPES, physical_type_compatible

_NEIGHBOR = {
    PropertyType.STRING: "INT64",
    PropertyType.INTEGER: "STRING",
    PropertyType.NUMBER: "INT64",
    PropertyType.BOOLEAN: "STRING",
    PropertyType.DATE: "DATETIME",
    PropertyType.DATETIME: "TIMESTAMP",
    PropertyType.TIME: "STRING",
    PropertyType.TIMESTAMP: "DATETIME",
    PropertyType.BYTES: "STRING",
    PropertyType.JSON: "STRING",
    PropertyType.GEOGRAPHY: "STRING",
}


@pytest.mark.parametrize("semantic", list(PropertyType))
def test_each_semantic_type_accepts_only_listed_physicals(semantic: PropertyType) -> None:
    allowed = COMPATIBLE_PHYSICAL_TYPES[semantic]
    for physical in allowed:
        assert physical_type_compatible(semantic, physical, "NULLABLE")
        assert physical_type_compatible(semantic, physical, "REQUIRED")
    assert not physical_type_compatible(semantic, _NEIGHBOR[semantic], "NULLABLE")


def test_number_accepts_float64_numeric_and_bignumeric() -> None:
    for physical in ("FLOAT64", "NUMERIC", "BIGNUMERIC"):
        assert physical_type_compatible(PropertyType.NUMBER, physical, "NULLABLE")


def test_integer_rejects_number_physicals() -> None:
    assert not physical_type_compatible(PropertyType.INTEGER, "FLOAT64", "NULLABLE")
    assert not physical_type_compatible(PropertyType.INTEGER, "NUMERIC", "NULLABLE")


def test_repeated_and_array_are_never_compatible() -> None:
    assert not physical_type_compatible(PropertyType.STRING, "STRING", "REPEATED")
    assert not physical_type_compatible(PropertyType.STRING, "ARRAY<STRING>", "NULLABLE")
    assert not physical_type_compatible(PropertyType.INTEGER, "STRUCT", "NULLABLE")


def test_google_integer_alias_is_not_silently_accepted() -> None:
    assert not physical_type_compatible(PropertyType.INTEGER, "INTEGER", "NULLABLE")
