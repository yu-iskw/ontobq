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

"""Mutation executor protocol. Live Google adapter lives in ``ontobq.bigquery.google``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MutationIdentity:
    """Project/dataset the executor is willing to mutate."""

    project: str
    dataset: str


@dataclass(frozen=True)
class MutationReceipt:
    """Outcome of one ``execute_ddl`` call. ``error`` set means the mutation failed."""

    job_id: str | None = None
    unchanged: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when the statement did not report an error."""

        return self.error is None


class MutationExecutor(Protocol):
    """Narrow DDL surface used by ``apply_plan``. Implementations must not compile SQL."""

    @property
    def identity(self) -> MutationIdentity: ...

    def execute_ddl(self, sql: str, *, target_name: str) -> MutationReceipt: ...
