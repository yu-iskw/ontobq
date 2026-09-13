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

"""Fail-fast E2E env gates. Unset allowlist never defaults to an ADC project."""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Mapping

ENABLE_ENV = "ONTOBQ_E2E"
PROJECT_ENV = "ONTOBQ_E2E_PROJECT"
DATASET_ENV = "ONTOBQ_E2E_DATASET"
ALLOWED_ENV = "ONTOBQ_E2E_ALLOWED_PROJECTS"
GRAPH_ENV = "ONTOBQ_E2E_GRAPH"
GRAPH_NAME = "commerce_e2e_graph"
DOMAIN_NAME = "commerce_e2e"
RFC_FIXTURE_PROJECT = "my-project"
_GRAPH_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class E2EDecision:
    """Resolved E2E gate. ``enabled`` is True only when DDL is allowed."""

    enabled: bool
    reason: str
    project: str
    dataset: str
    graph: str


def allowed_tokens(spec: str) -> tuple[str, ...]:
    """Split a comma-separated allowlist into stripped tokens."""

    return tuple(part.strip() for part in spec.split(",") if part.strip())


def token_matches(project: str, token: str) -> bool:
    """Exact project id, or prefix when the token ends with ``*``."""

    if token.endswith("*"):
        return project.startswith(token[:-1])
    return project == token


def project_is_allowed(project: str, spec: str) -> bool:
    """True when ``project`` matches an allowlist token."""

    return any(token_matches(project, token) for token in allowed_tokens(spec))


def decide_e2e(environ: Mapping[str, str]) -> E2EDecision:
    """Skip (do not DDL) unless enable flag, project, dataset, and allowlist pass."""

    graph = environ.get(GRAPH_ENV, "").strip() or GRAPH_NAME
    if environ.get(ENABLE_ENV, "") != "1":
        return E2EDecision(False, f"{ENABLE_ENV} is not 1", "", "", graph)
    project = environ.get(PROJECT_ENV, "").strip()
    dataset = environ.get(DATASET_ENV, "").strip()
    if not project or not dataset:
        return E2EDecision(False, f"{PROJECT_ENV} and {DATASET_ENV} are required", "", "", graph)
    if _GRAPH_ID.fullmatch(graph) is None:
        return E2EDecision(False, f"{GRAPH_ENV} is not a BigQuery identifier", project, dataset, graph)
    return _allowlist_decision(project, dataset, graph, environ.get(ALLOWED_ENV, "").strip())


def _allowlist_decision(project: str, dataset: str, graph: str, allowed: str) -> E2EDecision:
    if not allowed:
        return E2EDecision(False, f"{ALLOWED_ENV} is unset; refusing DDL", project, dataset, graph)
    if project == RFC_FIXTURE_PROJECT:
        return E2EDecision(False, "refusing RFC fixture project my-project", project, dataset, graph)
    if not project_is_allowed(project, allowed):
        reason = f"project {project} is not in {ALLOWED_ENV}"
        return E2EDecision(False, reason, project, dataset, graph)
    return E2EDecision(True, "", project, dataset, graph)
