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

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest  # pyright: ignore[reportMissingImports]

from ontobq import apply_plan, build_plan
from ontobq.bigquery.google import (
    GoogleBigQueryInspector,
    GoogleBigQueryReadExecutor,
    GoogleMutationExecutor,
)
from ontobq.tests.e2e.gates import DOMAIN_NAME, decide_e2e, new_run_id
from ontobq.tests.e2e.lifecycle import seed_statements, teardown_e2e
from ontobq.tests.e2e.templates import (
    HAPPY_YAML,
    SEED_FILES,
    RunCoordinates,
    materialize_file,
    materialize_text,
    sql_statements,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_THIS_DIR = Path(__file__).resolve().parent


def pytest_itemcollected(item: pytest.Item) -> None:
    """Mark every test collected under this directory ``e2e``.

    A bare module-level ``pytestmark`` in a ``conftest.py`` only marks tests
    defined in that same module; it does not propagate to sibling test modules
    such as ``test_mvp_happy_path.py``. Tagging here, as each item is
    collected (before ``-m`` marker expressions are evaluated), is what makes
    ``pytest -m e2e`` — and therefore ``make test-e2e`` — actually select
    every test under this directory. See ``test_e2e_marker_collection.py`` for
    an offline proof.
    """

    if _THIS_DIR in item.path.resolve().parents:
        item.add_marker(pytest.mark.e2e)


@dataclass(frozen=True)
class LiveE2E:
    """Session-scoped live BigQuery handles and materialized Domain YAML.

    ``domain_name`` and ``graph`` are unique per session (see ``run_id``) so
    parallel sessions sharing one allowlisted project/dataset never collide.
    """

    project: str
    dataset: str
    graph: str
    domain_name: str
    run_id: str
    workdir: Path
    domain_path: Path
    inspector: GoogleBigQueryInspector
    query_executor: GoogleBigQueryReadExecutor
    mutator: GoogleMutationExecutor

    @property
    def coords(self) -> RunCoordinates:
        """This session's project/dataset/graph/run-id template bundle."""

        return RunCoordinates(
            project=self.project, dataset=self.dataset, graph=self.graph, run_id=self.run_id
        )


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
        teardown_e2e(live.mutator, live.coords)


def _build_live(project: str, dataset: str, graph: str, workdir: Path) -> LiveE2E:
    run_id = new_run_id()
    run_graph = f"{graph}_{run_id}"
    coords = RunCoordinates(project=project, dataset=dataset, graph=run_graph, run_id=run_id)
    domain_path = materialize_file(HAPPY_YAML, workdir / HAPPY_YAML, coords)
    client = _bigquery_client(project)
    return LiveE2E(
        project=project,
        dataset=dataset,
        graph=run_graph,
        domain_name=f"{DOMAIN_NAME}_{run_id}",
        run_id=run_id,
        workdir=workdir,
        domain_path=domain_path,
        inspector=GoogleBigQueryInspector(client=client),
        query_executor=GoogleBigQueryReadExecutor(client=client),
        mutator=GoogleMutationExecutor(project=project, dataset=dataset),
    )


def _bigquery_client(project: str) -> object:
    """A single client bound to the gated project, shared by inspector and read executor.

    Without an explicit ``project=``, ``google.cloud.bigquery.Client()`` falls
    back to ADC's default project, which can silently differ from
    ``ONTOBQ_E2E_PROJECT``: metadata dry runs, integrity queries, and GQL
    queries would then run against (and bill) the wrong project. Binding both
    read-only adapters to this client keeps every live call scoped to the
    allowlisted project, matching ``GoogleMutationExecutor``.
    """

    return importlib.import_module("google.cloud.bigquery").Client(project=project)


def _seed(live: LiveE2E) -> None:
    for name in SEED_FILES:
        script = materialize_text(name, live.coords)
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
