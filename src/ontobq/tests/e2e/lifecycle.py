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

"""Seed and teardown this run's graph, views, and tables. Never DROP DATASET."""

from __future__ import annotations

from ontobq.bq.mutator import MutationExecutor, MutationReceipt
from ontobq.tests.e2e.templates import TEARDOWN_SQL, materialize_text, sql_statements


def qualified(project: str, dataset: str, name: str) -> str:
    """Return ``project.dataset.name``."""

    return f"{project}.{dataset}.{name}"


def graph_target(project: str, dataset: str, graph: str) -> str:
    """Qualified property-graph name."""

    return qualified(project, dataset, graph)


def run_ddl(executor: MutationExecutor, sql: str, target_name: str) -> MutationReceipt:
    """Execute one statement and raise if the live mutator reported an error."""

    receipt = executor.execute_ddl(sql, target_name=target_name)
    if not receipt.ok:
        raise RuntimeError(receipt.error or f"DDL failed for {target_name}")
    return receipt


def seed_statements(executor: MutationExecutor, statements: tuple[str, ...], label: str) -> None:
    """Run seed SQL statements in order through the live mutator."""

    for index, statement in enumerate(statements):
        run_ddl(executor, statement, target_name=f"{label}:{index}")


def teardown_e2e(executor: MutationExecutor, project: str, dataset: str, graph: str) -> None:
    """Run fixtures/teardown.sql. Never DROP DATASET."""

    script = materialize_text(TEARDOWN_SQL, project, dataset, graph)
    seed_statements(executor, sql_statements(script), label="teardown")
