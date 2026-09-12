# Copyright 2025 yu-iskw
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""BigQuery metadata inspector protocol, DTOs, and duck-typed SDK adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

_TYPE_ALIASES = {
    "INTEGER": "INT64",
    "INT64": "INT64",
    "BOOLEAN": "BOOL",
    "BOOL": "BOOL",
    "FLOAT": "FLOAT64",
    "FLOAT64": "FLOAT64",
}
_SUPPORTED_KINDS = frozenset({"TABLE", "VIEW"})


@dataclass(frozen=True)
class SourceSnapshot:
    """Metadata for one mapped table or view. Missing sources set ``exists=False``."""

    table_id: str
    exists: bool
    kind: str
    location: str | None


@dataclass(frozen=True)
class ColumnSnapshot:
    """One schema field. ``mode`` is ``NULLABLE``, ``REQUIRED``, or ``REPEATED``."""

    name: str
    type: str
    mode: str


@dataclass(frozen=True)
class ScalarDryRunResult:
    """Type-analysis result for one trusted scalar mapping expression."""

    ok: bool
    type: str | None
    error: str | None


class BigQueryInspector(Protocol):
    """Read-only BigQuery I/O surface for Layer 3 metadata validation."""

    def get_source(self, table_id: str) -> SourceSnapshot:
        """Return table/view metadata. Missing sources are ``exists=False``."""
        raise NotImplementedError

    def get_columns(self, table_id: str) -> tuple[ColumnSnapshot, ...]:
        """Return schema fields. Missing sources return an empty tuple."""
        raise NotImplementedError

    def dry_run_scalar_expression(self, source: str, expression: str) -> ScalarDryRunResult:
        """Type-analyze ``expression`` in ``source`` without reading row data."""
        raise NotImplementedError

    def get_location(self, resource: str) -> str | None:
        """Return the location of a table or dataset, or ``None`` if missing."""
        raise NotImplementedError


class SdkShapedClient(Protocol):
    """Duck-typed subset of the Google BigQuery client used by ClientInspector."""

    def get_table(self, table_id: str) -> object:
        """Return a table object or raise a missing-resource error."""
        raise NotImplementedError

    def get_dataset(self, dataset_id: str) -> object:
        """Return a dataset object or raise a missing-resource error."""
        raise NotImplementedError

    def query(self, sql: str, job_config: object | None = None) -> object:
        """Start a query job (dry-run when ``job_config`` says so)."""
        raise NotImplementedError


def scalar_expression_dry_run_sql(source: str, expression: str) -> str:
    """Adapter-private type-probe SQL. Compilers must copy expression text, not this wrapper."""

    return f"SELECT (({expression})) AS __ontobq_type_probe\nFROM `{source}`\nWHERE FALSE"


def canonicalize_bq_type(raw: str) -> str:
    """Map Google aliases such as ``INTEGER`` to canonical names. Not a coercion."""

    compact = raw.strip().upper().replace(" ", "")
    return _TYPE_ALIASES.get(compact, compact)


def canonicalize_location(location: str | None) -> str | None:
    """Strip and uppercase a location id. ``US`` stays distinct from ``us-central1``."""

    if location is None:
        return None
    stripped = location.strip()
    if not stripped:
        return None
    return stripped.upper()


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _table_location(table: object) -> str | None:
    return canonicalize_location(_optional_str(getattr(table, "location", None)))


def _snapshot_from_table(table_id: str, table: object) -> SourceSnapshot:
    kind = str(getattr(table, "table_type", "") or "")
    return SourceSnapshot(
        table_id=table_id,
        exists=True,
        kind=kind,
        location=_table_location(table),
    )


def _column_from_field(field: object) -> ColumnSnapshot:
    mode = str(getattr(field, "mode", "NULLABLE") or "NULLABLE")
    return ColumnSnapshot(
        name=str(getattr(field, "name", "")),
        type=canonicalize_bq_type(str(getattr(field, "field_type", ""))),
        mode=mode.upper(),
    )


def _columns_from_table(table: object) -> tuple[ColumnSnapshot, ...]:
    schema = getattr(table, "schema", None) or ()
    return tuple(_column_from_field(field) for field in schema)


def _schema_result(job: object) -> ScalarDryRunResult:
    schema = getattr(job, "schema", None) or ()
    if not schema:
        return ScalarDryRunResult(ok=True, type=None, error=None)
    field_type = canonicalize_bq_type(str(getattr(schema[0], "field_type", "")))
    return ScalarDryRunResult(ok=True, type=field_type, error=None)


class ClientInspector:
    """Inspector over a duck-typed BigQuery client (SDK or in-memory fake)."""

    def __init__(
        self,
        client: SdkShapedClient,
        not_found: type[BaseException],
        query_errors: tuple[type[BaseException], ...],
        job_config_type: Callable[..., object],
    ) -> None:
        self._client = client
        self._not_found = not_found
        self._query_errors = query_errors
        self._job_config_type = job_config_type

    def _get_table(self, table_id: str) -> object | None:
        try:
            return self._client.get_table(table_id)
        except self._not_found:
            return None

    def get_source(self, table_id: str) -> SourceSnapshot:
        table = self._get_table(table_id)
        if table is None:
            return SourceSnapshot(table_id=table_id, exists=False, kind="", location=None)
        return _snapshot_from_table(table_id, table)

    def get_columns(self, table_id: str) -> tuple[ColumnSnapshot, ...]:
        table = self._get_table(table_id)
        if table is None:
            return ()
        return _columns_from_table(table)

    def _dry_run_job_config(self) -> object:
        return self._job_config_type(dry_run=True, use_query_cache=False)

    def _query_dry_run(self, sql: str, job_config: object) -> ScalarDryRunResult:
        try:
            job = self._client.query(sql, job_config=job_config)
        except self._query_errors as exc:
            return ScalarDryRunResult(ok=False, type=None, error=str(exc))
        return _schema_result(job)

    def dry_run_scalar_expression(self, source: str, expression: str) -> ScalarDryRunResult:
        sql = scalar_expression_dry_run_sql(source, expression)
        return self._query_dry_run(sql, self._dry_run_job_config())

    def _dataset_location(self, resource: str) -> str | None:
        try:
            dataset = self._client.get_dataset(resource)
        except self._not_found:
            return None
        return canonicalize_location(_optional_str(getattr(dataset, "location", None)))

    def get_location(self, resource: str) -> str | None:
        table = self._get_table(resource)
        if table is not None:
            return _table_location(table)
        return self._dataset_location(resource)


def is_supported_source_kind(kind: str) -> bool:
    """v1alpha1 supports TABLE and VIEW only."""

    return kind.strip().upper() in _SUPPORTED_KINDS
