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
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


def project_is_allowed(project: str, spec: str) -> bool:
    """True when ``project`` is an *exact*, trimmed member of the allowlist.

    No wildcard/prefix matching: a token such as ``*`` or ``prod*`` must never
    authorize an entire project family. Every allowlist entry must name a
    concrete project id.
    """

    return project in allowed_tokens(spec)


def new_run_id() -> str:
    """Identifier-safe, low-collision suffix so parallel E2E sessions never collide.

    Applied to the materialized domain name, graph, seed tables, generated
    views, and isolated negative-case tables (see ``templates.RUN_ID_TOKEN``)
    so two sessions sharing one allowlisted project/dataset create and tear
    down disjoint objects instead of overwriting or dropping each other's.
    """

    return secrets.token_hex(4)


def decide_e2e(environ: Mapping[str, str]) -> E2EDecision:
    """Skip (do not DDL) unless enable flag, project, dataset, and allowlist pass."""

    graph = environ.get(GRAPH_ENV, "").strip() or GRAPH_NAME
    project = environ.get(PROJECT_ENV, "").strip()
    dataset = environ.get(DATASET_ENV, "").strip()
    reason = _basic_gate_reason(environ, project, dataset, graph)
    if reason:
        return E2EDecision(False, reason, project, dataset, graph)
    return _allowlist_decision(project, dataset, graph, environ.get(ALLOWED_ENV, "").strip())


def _basic_gate_reason(environ: Mapping[str, str], project: str, dataset: str, graph: str) -> str:
    """Return a refusal reason for the enable/project/dataset/graph-id gates, or ``""``."""

    checks = (
        (environ.get(ENABLE_ENV, "") != "1", f"{ENABLE_ENV} is not 1"),
        (not project or not dataset, f"{PROJECT_ENV} and {DATASET_ENV} are required"),
        (_GRAPH_ID.fullmatch(graph) is None, f"{GRAPH_ENV} is not a BigQuery identifier"),
    )
    for failed, reason in checks:
        if failed:
            return reason
    return ""


def _allowlist_decision(project: str, dataset: str, graph: str, allowed: str) -> E2EDecision:
    """True only when the allowlist and RFC-fixture-project gates both pass."""

    reason = _allowlist_reason(project, allowed)
    return E2EDecision(not reason, reason, project, dataset, graph)


def _allowlist_reason(project: str, allowed: str) -> str:
    """Return a refusal reason for the allowlist gate, or ``""`` when it passes."""

    checks = (
        (not allowed, f"{ALLOWED_ENV} is unset; refusing DDL"),
        (project == RFC_FIXTURE_PROJECT, "refusing RFC fixture project my-project"),
        (not project_is_allowed(project, allowed), f"project {project} is not in {ALLOWED_ENV}"),
    )
    for failed, reason in checks:
        if failed:
            return reason
    return ""
