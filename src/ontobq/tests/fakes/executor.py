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

"""In-memory MutationExecutor. Records submitted SQL; never talks to BigQuery."""

from __future__ import annotations

from ontobq.bq.mutator import MutationIdentity, MutationReceipt


class FakeMutationExecutor:
    """Configurable identity, optional failure target, and last-SQL map for reapply."""

    def __init__(
        self,
        *,
        project: str = "my-project",
        dataset: str = "semantic",
        fail_at_target: str | None = None,
        fail_message: str = "injected failure",
    ) -> None:
        self._identity = MutationIdentity(project=project, dataset=dataset)
        self.fail_at_target = fail_at_target
        self.fail_message = fail_message
        self.submitted: list[tuple[str, str]] = []
        self.definitions: dict[str, str] = {}

    @property
    def identity(self) -> MutationIdentity:
        return self._identity

    def execute_ddl(self, sql: str, *, target_name: str) -> MutationReceipt:
        self.submitted.append((target_name, sql))
        if self.fail_at_target == target_name:
            return MutationReceipt(error=self.fail_message)
        unchanged = self.definitions.get(target_name) == sql
        self.definitions[target_name] = sql
        return MutationReceipt(unchanged=unchanged)
