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

"""Read-only query executor protocol and in-process fake for integrity checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


@dataclass(frozen=True)
class QueryEstimate:
    """Dry-run cost estimate. Integrity never skips checks based on this."""

    bytes_processed: int = 0


class BigQueryReadExecutor(Protocol):
    """Read-only BigQuery query surface used by data-integrity validation.

    Implementations must not mutate resources. ``max_rows`` is a hard cap on
    returned rows; do not silently sample the scanned table.
    """

    def dry_run(self, sql: str) -> QueryEstimate: ...

    def query(self, sql: str, *, max_rows: int) -> Sequence[Mapping[str, object]]: ...


@dataclass(frozen=True)
class FakeQueryCall:
    """One ``query`` invocation recorded by :class:`FakeBigQueryReadExecutor`."""

    sql: str
    max_rows: int


class FakeBigQueryReadExecutor:
    """Scripted read-only executor for unit tests. Not a mock of the compiler."""

    def __init__(
        self,
        rows_by_sql: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    ) -> None:
        self.rows_by_sql = {sql: tuple(rows) for sql, rows in (rows_by_sql or {}).items()}
        self.dry_run_calls: list[str] = []
        self.query_calls: list[FakeQueryCall] = []

    def dry_run(self, sql: str) -> QueryEstimate:
        self.dry_run_calls.append(sql)
        return QueryEstimate(bytes_processed=0)

    def query(self, sql: str, *, max_rows: int) -> tuple[Mapping[str, object], ...]:
        if max_rows < 0:
            raise ValueError("max_rows must be >= 0")
        self.query_calls.append(FakeQueryCall(sql=sql, max_rows=max_rows))
        rows = self.rows_by_sql.get(sql, ())
        return rows[:max_rows]
