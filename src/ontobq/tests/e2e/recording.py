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

"""Recording MutationExecutor wrapper. Forwards to a live executor; not a fake."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ontobq.bq.mutator import MutationExecutor, MutationIdentity, MutationReceipt


class RecordingMutationExecutor:
    """Count ``execute_ddl`` calls while forwarding to the inner live mutator."""

    def __init__(self, inner: MutationExecutor) -> None:
        self._inner = inner
        self.calls: list[tuple[str, str]] = []

    @property
    def identity(self) -> MutationIdentity:
        return self._inner.identity

    def execute_ddl(self, sql: str, *, target_name: str) -> MutationReceipt:
        self.calls.append((target_name, sql))
        return self._inner.execute_ddl(sql, target_name=target_name)
