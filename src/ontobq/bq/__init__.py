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

"""BigQuery query and mutation adapters."""

from ontobq.bq.executor import (
    BigQueryReadExecutor,
    FakeBigQueryReadExecutor,
    FakeQueryCall,
    QueryEstimate,
)
from ontobq.bq.mutator import MutationExecutor, MutationIdentity, MutationReceipt

__all__ = [
    "BigQueryReadExecutor",
    "FakeBigQueryReadExecutor",
    "FakeQueryCall",
    "MutationExecutor",
    "MutationIdentity",
    "MutationReceipt",
    "QueryEstimate",
]
