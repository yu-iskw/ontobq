"""validate_integrity against FakeBigQueryReadExecutor. No mocks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest  # pyright: ignore[reportMissingImports]

from ontobq import (
    FakeBigQueryReadExecutor,
    IntegrityExecutionError,
    QueryEstimate,
    compile_integrity_queries,
    load_domain,
    validate_integrity,
)
from ontobq.diagnostics import Severity
from ontobq.tests.paths import FIXTURES_DIR
from ontobq.validate.integrity import DEFAULT_EVIDENCE_LIMIT

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class _BoomExecutor:
    def dry_run(self, sql: str) -> QueryEstimate:
        raise RuntimeError(f"unavailable: {sql[:12]}")

    def query(self, sql: str, *, max_rows: int) -> Sequence[Mapping[str, object]]:
        raise RuntimeError(f"should not query {sql} max_rows={max_rows}")


def test_empty_rows_yield_no_diagnostics() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    report = validate_integrity(domain, FakeBigQueryReadExecutor())
    assert not report.diagnostics
    assert len(report.queries) == len(compile_integrity_queries(domain))
    assert report.queries[0].code == "OBQ201"


def test_execute_false_does_not_call_executor() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    executor = _BoomExecutor()
    report = validate_integrity(domain, executor, execute=False)
    assert not report.diagnostics
    assert [item.sql for item in report.queries] == [
        item.sql for item in compile_integrity_queries(domain)
    ]


def test_scripted_violations_are_bounded() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    limit = DEFAULT_EVIDENCE_LIMIT
    total_violations = 100
    queries = compile_integrity_queries(domain, evidence_limit=limit)
    customer_null = next(
        item for item in queries if item.code == "OBQ201" and item.element == "Customer"
    )
    extra_rows = 5
    rows = (
        {"id": None, "violation_count": extra_rows, "total_violations": total_violations},
        *(
            {
                "id": f"id-{index}",
                "violation_count": 2,
                "total_violations": total_violations,
            }
            for index in range(limit + extra_rows - 1)
        ),
    )
    executor = FakeBigQueryReadExecutor({customer_null.sql: rows})
    report = validate_integrity(domain, executor, evidence_limit=limit)
    assert len(executor.query_calls) == len(queries)
    assert {call.max_rows for call in executor.query_calls} == {limit}
    assert len(executor.dry_run_calls) == len(queries)
    assert executor.query_calls[0].max_rows == customer_null.evidence_limit
    assert len(report.diagnostics) == 1
    diagnostic = report.diagnostics[0]
    assert diagnostic.code == "OBQ201"
    assert diagnostic.severity is Severity.ERROR
    assert diagnostic.path == "spec.entities.Customer.key"
    assert diagnostic.message == "entity key contains NULL"
    assert diagnostic.evidence[0] == f"total_violations={total_violations}"
    assert diagnostic.evidence[1] == f"id=<NULL> count={extra_rows}"
    assert diagnostic.evidence[-1] == f"truncated=true shown={limit}"
    assert len(diagnostic.evidence) == limit + 2


def test_unique_violation_evidence_includes_counts() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    query = next(
        item
        for item in compile_integrity_queries(domain)
        if item.code == "OBQ202" and item.element == "Customer"
    )
    duplicate_count = 3
    executor = FakeBigQueryReadExecutor(
        {query.sql: ({"id": "alice", "violation_count": duplicate_count, "total_violations": 1},)}
    )
    report = validate_integrity(domain, executor)
    assert report.diagnostics[0].evidence == (
        "total_violations=1",
        f"id=alice count={duplicate_count}",
    )


def test_zero_total_violations_yields_no_diagnostic() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    query = compile_integrity_queries(domain)[0]
    executor = FakeBigQueryReadExecutor(
        {query.sql: ({"id": None, "violation_count": 1, "total_violations": 0},)}
    )
    report = validate_integrity(domain, executor)
    assert not report.diagnostics


def test_string_violation_counts_are_parsed() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    query = next(
        item
        for item in compile_integrity_queries(domain)
        if item.code == "OBQ202" and item.element == "Customer"
    )
    executor = FakeBigQueryReadExecutor(
        {query.sql: ({"id": "alice", "violation_count": "3", "total_violations": "1"},)}
    )
    [diagnostic] = validate_integrity(domain, executor).diagnostics
    assert diagnostic.evidence == ("total_violations=1", "id=alice count=3")


def test_fake_executor_rejects_negative_max_rows() -> None:
    executor = FakeBigQueryReadExecutor()
    with pytest.raises(ValueError, match="max_rows"):
        executor.query("SELECT 1", max_rows=-1)


def test_execution_failure_raises_dedicated_error() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    with pytest.raises(IntegrityExecutionError) as caught:
        validate_integrity(domain, _BoomExecutor())
    assert caught.value.query.code == "OBQ201"
    message = str(caught.value)
    assert "OBQ101" not in message
    assert "OBQ105" not in message
    assert isinstance(caught.value.__cause__, RuntimeError)


class _DriverError(Exception):
    """Custom executor failure outside OSError/RuntimeError/ValueError/TypeError."""


class _DriverExecutor:
    def dry_run(self, sql: str) -> QueryEstimate:
        raise _DriverError(f"rpc failed: {sql[:12]}")

    def query(self, sql: str, *, max_rows: int) -> Sequence[Mapping[str, object]]:
        raise _DriverError(f"should not query {sql} max_rows={max_rows}")


class _QueryDriverExecutor:
    def dry_run(self, sql: str) -> QueryEstimate:
        return QueryEstimate(bytes_processed=len(sql) * 0)

    def query(self, sql: str, *, max_rows: int) -> Sequence[Mapping[str, object]]:
        raise _DriverError(f"rows unavailable {sql[:8]} {max_rows}")


def test_custom_executor_exception_is_wrapped() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    with pytest.raises(IntegrityExecutionError) as caught:
        validate_integrity(domain, _DriverExecutor())
    assert caught.value.query.code == "OBQ201"
    assert isinstance(caught.value.__cause__, _DriverError)


def test_custom_query_exception_is_wrapped() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    with pytest.raises(IntegrityExecutionError) as caught:
        validate_integrity(domain, _QueryDriverExecutor())
    assert caught.value.query.element == "Customer"
    assert isinstance(caught.value.__cause__, _DriverError)


def test_malformed_total_violations_raises_integrity_error() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    query = compile_integrity_queries(domain)[0]
    executor = FakeBigQueryReadExecutor(
        {query.sql: ({"id": "alice", "violation_count": 1, "total_violations": "invalid"},)}
    )
    with pytest.raises(IntegrityExecutionError) as caught:
        validate_integrity(domain, executor)
    assert caught.value.query == query
    assert isinstance(caught.value.__cause__, ValueError)
    assert "total_violations" in str(caught.value.__cause__)


def test_boolean_total_violations_raises_integrity_error() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    query = compile_integrity_queries(domain)[0]
    executor = FakeBigQueryReadExecutor(
        {query.sql: ({"id": "alice", "violation_count": 1, "total_violations": True},)}
    )
    with pytest.raises(IntegrityExecutionError) as caught:
        validate_integrity(domain, executor)
    assert caught.value.query == query
    assert isinstance(caught.value.__cause__, TypeError)


def test_malformed_violation_count_raises_integrity_error() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    query = compile_integrity_queries(domain)[0]
    executor = FakeBigQueryReadExecutor(
        {query.sql: ({"id": "alice", "violation_count": "bad", "total_violations": 1},)}
    )
    with pytest.raises(IntegrityExecutionError) as caught:
        validate_integrity(domain, executor)
    assert caught.value.query.code == query.code
    assert isinstance(caught.value.__cause__, ValueError)
    assert "violation_count" in str(caught.value.__cause__)
