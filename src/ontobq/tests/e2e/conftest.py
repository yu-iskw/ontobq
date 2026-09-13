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

"""Skip live mutations unless ONTOBQ_E2E=1 and the project/dataset are allowlisted."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from ontobq import apply_plan, build_plan
from ontobq.bigquery.google import (
    GoogleBigQueryInspector,
    GoogleBigQueryReadExecutor,
    GoogleMutationExecutor,
)
from ontobq.tests.e2e.gates import decide_e2e
from ontobq.tests.e2e.lifecycle import seed_statements, teardown_e2e
from ontobq.tests.e2e.templates import (
    HAPPY_YAML,
    SEED_FILES,
    materialize_file,
    materialize_text,
    sql_statements,
)

pytestmark = pytest.mark.e2e


@dataclass(frozen=True)
class LiveE2E:
    """Session-scoped live BigQuery handles and materialized Domain YAML."""

    project: str
    dataset: str
    graph: str
    workdir: Path
    domain_path: Path
    inspector: GoogleBigQueryInspector
    query_executor: GoogleBigQueryReadExecutor
    mutator: GoogleMutationExecutor


@pytest.fixture(scope="session")
def e2e_live(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveE2E]:
    """Seed isolated tables, apply the happy Domain, then drop this run's objects."""

    decision = decide_e2e(os.environ)
    if not decision.enabled:
        pytest.skip(decision.reason)
    workdir = tmp_path_factory.mktemp("ontobq-e2e")
    live = _build_live(decision.project, decision.dataset, decision.graph, workdir)
    try:
        _seed(live)
        _apply_happy(live)
        yield live
    finally:
        teardown_e2e(live.mutator, live.project, live.dataset, live.graph)


def _build_live(project: str, dataset: str, graph: str, workdir: Path) -> LiveE2E:
    domain_path = materialize_file(HAPPY_YAML, workdir / HAPPY_YAML, project, dataset, graph)
    return LiveE2E(
        project=project,
        dataset=dataset,
        graph=graph,
        workdir=workdir,
        domain_path=domain_path,
        inspector=GoogleBigQueryInspector(),
        query_executor=GoogleBigQueryReadExecutor(),
        mutator=GoogleMutationExecutor(project=project, dataset=dataset),
    )


def _seed(live: LiveE2E) -> None:
    for name in SEED_FILES:
        script = materialize_text(name, live.project, live.dataset, live.graph)
        seed_statements(live.mutator, sql_statements(script), label=name)


def _apply_happy(live: LiveE2E) -> None:
    plan = build_plan(
        live.domain_path,
        inspector=live.inspector,
        query_executor=live.query_executor,
    )
    result = apply_plan(plan, live.mutator)
    if not result.ok:
        raise RuntimeError(f"happy-path apply failed: {result.refusal_reasons}")
