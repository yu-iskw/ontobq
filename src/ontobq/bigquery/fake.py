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

"""In-memory BigQueryInspector for tests and offline validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ontobq.bigquery.inspector import ColumnSnapshot, ScalarDryRunResult, SourceSnapshot

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class FakeCatalog:
    """Configured physical catalog overlayed onto Domain mapping sources."""

    sources: Mapping[str, SourceSnapshot] = field(default_factory=dict)
    columns: Mapping[str, tuple[ColumnSnapshot, ...]] = field(default_factory=dict)
    locations: Mapping[str, str | None] = field(default_factory=dict)
    dry_runs: Mapping[tuple[str, str], ScalarDryRunResult] = field(default_factory=dict)


def _source_location(snapshot: SourceSnapshot | None) -> str | None:
    if snapshot is None:
        return None
    return snapshot.location


class FakeBigQueryInspector:
    """Production Protocol implementation backed by an in-memory catalog."""

    def __init__(self, catalog: FakeCatalog | None = None) -> None:
        self._catalog = catalog if catalog is not None else FakeCatalog()

    def get_source(self, table_id: str) -> SourceSnapshot:
        snapshot = self._catalog.sources.get(table_id)
        if snapshot is None:
            return SourceSnapshot(table_id=table_id, exists=False, kind="", location=None)
        return snapshot

    def get_columns(self, table_id: str) -> tuple[ColumnSnapshot, ...]:
        return tuple(self._catalog.columns.get(table_id, ()))

    def dry_run_scalar_expression(self, source: str, expression: str) -> ScalarDryRunResult:
        configured = self._catalog.dry_runs.get((source, expression))
        if configured is None:
            return ScalarDryRunResult(ok=False, type=None, error="expression was not configured")
        return configured

    def get_location(self, resource: str) -> str | None:
        if resource in self._catalog.locations:
            return self._catalog.locations[resource]
        return _source_location(self._catalog.sources.get(resource))
