"""Google adapter isolation: SDK imports stay in bigquery/google.py."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import ontobq
from ontobq.bigquery.google import GoogleBigQueryReadExecutor

if TYPE_CHECKING:
    from collections.abc import Mapping

_ADAPTER = Path(ontobq.__file__).resolve().parent / "bigquery" / "google.py"


class _ResultOnlyJob:
    """SDK-shaped QueryJob: rows are available only from ``result()``."""

    def __init__(self, rows: tuple[Mapping[str, object], ...]) -> None:
        self._rows = rows

    def __iter__(self) -> object:
        raise AssertionError("iterate QueryJob.result() rows, not the job")

    def result(self) -> tuple[Mapping[str, object], ...]:
        return self._rows


class _ResultOnlyClient:
    """Duck-typed BigQuery client that returns a result-only job."""

    def __init__(self, job: _ResultOnlyJob) -> None:
        self._job = job
        self.sql: str | None = None

    def query(self, sql: str, job_config: object | None = None) -> _ResultOnlyJob:
        self.sql = sql
        self.job_config = job_config
        return self._job


def test_google_adapter_contains_dry_run_config() -> None:
    text = _ADAPTER.read_text(encoding="utf-8")
    assert "google.cloud" in text
    assert "QueryJobConfig" in text
    assert "GoogleBigQueryInspector" in text
    assert "GoogleBigQueryReadExecutor" in text
    assert "job.result()" in text
    assert "CREATE OR REPLACE VIEW" not in text
    assert "PROPERTY GRAPH" not in text


def test_only_google_adapter_imports_google_cloud() -> None:
    root = Path(ontobq.__file__).resolve().parent
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or path == _ADAPTER:
            continue
        text = path.read_text(encoding="utf-8")
        if "google.cloud" in text or "from google" in text:
            offenders.append(str(path.relative_to(root)))
    assert not offenders


def test_read_executor_query_uses_job_result_and_max_rows() -> None:
    rows = ({"id": "a"}, {"id": "b"}, {"id": "c"})
    job = _ResultOnlyJob(rows)
    client = _ResultOnlyClient(job)
    executor = GoogleBigQueryReadExecutor(client)
    got = executor.query("SELECT id FROM t", max_rows=2)
    assert client.sql == "SELECT id FROM t"
    assert got == ({"id": "a"}, {"id": "b"})
