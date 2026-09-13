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

"""Google Cloud BigQuery adapter. The only production module that imports google.cloud."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, cast

from ontobq.bigquery.inspector import ClientInspector, SdkShapedClient
from ontobq.bq.executor import QueryEstimate
from ontobq.bq.mutator import MutationIdentity, MutationReceipt

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = ["GoogleBigQueryInspector", "GoogleBigQueryReadExecutor", "GoogleMutationExecutor"]


def _load_bigquery() -> Any:
    return importlib.import_module("google.cloud.bigquery")


def _load_exceptions() -> Any:
    return importlib.import_module("google.api_core.exceptions")


def _sdk_client(client: object | None, sdk: Any) -> SdkShapedClient:
    if client is not None:
        return cast("SdkShapedClient", client)
    return cast("SdkShapedClient", sdk.Client())


class GoogleBigQueryInspector(ClientInspector):
    """Read-only metadata inspector backed by ``google.cloud.bigquery.Client``."""

    def __init__(self, client: object | None = None) -> None:
        sdk = _load_bigquery()
        errors = _load_exceptions()
        super().__init__(
            _sdk_client(client, sdk),
            errors.NotFound,
            (errors.BadRequest, errors.NotFound),
            sdk.QueryJobConfig,
        )


def _bytes_processed(job: object) -> int:
    processed = getattr(job, "total_bytes_processed", 0) or 0
    return int(processed)


def _row_mapping(row: object) -> dict[str, object]:
    items = cast("Mapping[object, object]", row).items()
    return {str(key): value for key, value in items}


def _rows_from_job(job: object, max_rows: int) -> tuple[Mapping[str, object], ...]:
    rows: list[Mapping[str, object]] = []
    for index, row in enumerate(cast("Iterable[object]", job)):
        if index >= max_rows:
            break
        rows.append(_row_mapping(row))
    return tuple(rows)


class GoogleBigQueryReadExecutor:
    """Read-only query executor backed by ``google.cloud.bigquery.Client``."""

    def __init__(self, client: object | None = None) -> None:
        self._job_config_cls: Any = None
        if client is None:
            sdk = _load_bigquery()
            self._client: Any = _sdk_client(None, sdk)
            self._job_config_cls = sdk.QueryJobConfig
            return
        self._client = client

    def dry_run(self, sql: str) -> QueryEstimate:
        config_cls = self._job_config_cls
        if config_cls is None:
            config_cls = _load_bigquery().QueryJobConfig
            self._job_config_cls = config_cls
        job = self._client.query(sql, job_config=config_cls(dry_run=True, use_query_cache=False))
        return QueryEstimate(bytes_processed=_bytes_processed(job))

    def query(self, sql: str, *, max_rows: int) -> tuple[Mapping[str, object], ...]:
        if max_rows < 0:
            raise ValueError("max_rows must be >= 0")
        job = self._client.query(sql)
        return _rows_from_job(job.result(), max_rows)


def _optional_job_id(job: object) -> str | None:
    job_id = getattr(job, "job_id", None)
    if job_id is None:
        return None
    return str(job_id)


def _wait_for_job(job: object) -> None:
    result_fn = getattr(job, "result", None)
    if callable(result_fn):
        result_fn()


def _client_for_project(sdk: Any, project: str) -> Any:
    return sdk.Client(project=project)


class GoogleMutationExecutor:
    """DDL executor backed by ``google.cloud.bigquery.Client``. Success is always applied."""

    def __init__(
        self,
        *,
        project: str,
        dataset: str,
        client: object | None = None,
    ) -> None:
        self._identity = MutationIdentity(project=project, dataset=dataset)
        if client is not None:
            self._client: Any = client
            return
        sdk = _load_bigquery()
        self._client = _client_for_project(sdk, project)

    @property
    def identity(self) -> MutationIdentity:
        return self._identity

    def execute_ddl(self, sql: str, *, target_name: str) -> MutationReceipt:
        del target_name
        try:
            job = self._client.query(sql)
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            return MutationReceipt(error=str(error))
        try:
            _wait_for_job(job)
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            return MutationReceipt(job_id=_optional_job_id(job), error=str(error))
        return MutationReceipt(job_id=_optional_job_id(job))
