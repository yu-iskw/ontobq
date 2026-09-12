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

"""Read-only BigQuery inspection. The Google SDK adapter is ``ontobq.bigquery.google``."""

from ontobq.bigquery.fake import FakeBigQueryInspector, FakeCatalog
from ontobq.bigquery.inspector import (
    BigQueryInspector,
    ClientInspector,
    ColumnSnapshot,
    ScalarDryRunResult,
    SourceSnapshot,
    canonicalize_bq_type,
    canonicalize_location,
    is_supported_source_kind,
    scalar_expression_dry_run_sql,
)

__all__ = [
    "BigQueryInspector",
    "ClientInspector",
    "ColumnSnapshot",
    "FakeBigQueryInspector",
    "FakeCatalog",
    "ScalarDryRunResult",
    "SourceSnapshot",
    "canonicalize_bq_type",
    "canonicalize_location",
    "is_supported_source_kind",
    "scalar_expression_dry_run_sql",
]
