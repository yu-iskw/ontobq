"""Google adapter isolation: SDK imports stay in bigquery/google.py."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import ontobq
from ontobq.bigquery.google import (
    GoogleBigQueryReadExecutor,
    GoogleMutationExecutor,
    _client_for_project,
)

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
    assert "GoogleMutationExecutor" in text
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


class _DdlJob:
    """SDK-shaped job that yields a job id after result()."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.finished = False

    def result(self) -> None:
        self.finished = True


class _DdlClient:
    """Duck-typed BigQuery client for mutation tests."""

    def __init__(self, job: _DdlJob) -> None:
        self._job = job
        self.sql: str | None = None

    def query(self, sql: str, job_config: object | None = None) -> _DdlJob:
        del job_config
        self.sql = sql
        return self._job


class _FailingDdlClient:
    def query(self, sql: str, job_config: object | None = None) -> object:
        del sql, job_config
        raise RuntimeError("ddl failed")


def test_mutation_executor_success_is_applied_with_job_id() -> None:
    job = _DdlJob("job-123")
    client = _DdlClient(job)
    executor = GoogleMutationExecutor(project="my-project", dataset="semantic", client=client)
    receipt = executor.execute_ddl("SELECT 1", target_name="my-project.semantic.view")
    assert client.sql == "SELECT 1"
    assert job.finished is True
    assert receipt.ok
    assert receipt.unchanged is False
    assert receipt.job_id == "job-123"


def test_mutation_executor_sdk_error_returns_receipt() -> None:
    executor = GoogleMutationExecutor(
        project="my-project",
        dataset="semantic",
        client=_FailingDdlClient(),
    )
    receipt = executor.execute_ddl("SELECT 1", target_name="t")
    assert not receipt.ok
    assert receipt.error == "ddl failed"


class _ProjectRecordingSdk:
    """Duck-typed SDK: records Client(project=...)."""

    def __init__(self) -> None:
        self.project: str | None = None
        self.Client = self._client

    def _client(self, project: str | None = None) -> object:
        self.project = project
        return object()


def test_mutation_live_client_uses_configured_project() -> None:
    sdk = _ProjectRecordingSdk()
    _client_for_project(sdk, "my-project")
    assert sdk.project == "my-project"
