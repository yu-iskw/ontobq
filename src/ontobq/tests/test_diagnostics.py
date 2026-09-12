"""Shared Diagnostic type freeze."""

from __future__ import annotations

from ontobq import Diagnostic, Severity


def test_diagnostic_fields() -> None:
    diagnostic = Diagnostic(
        code="OBQ005",
        severity=Severity.ERROR,
        path="spec.relationships.PLACED.mapping.bigquery.from",
        message="endpoint mapping keys do not match",
    )
    assert diagnostic.code == "OBQ005"
    assert diagnostic.path == "spec.relationships.PLACED.mapping.bigquery.from"
    assert diagnostic.message == "endpoint mapping keys do not match"


def test_diagnostic_severity_enum() -> None:
    error = Diagnostic(code="OBQ000", severity=Severity.ERROR, path="$", message="bad")
    warning = Diagnostic(code="OBQ000", severity=Severity.WARNING, path="$", message="bad")
    assert error.severity is Severity.ERROR
    assert warning.severity is Severity.WARNING
    assert error.severity != warning.severity
