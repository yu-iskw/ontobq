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

"""Deterministic human and JSON presentation for validate/plan results."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from ontobq.diagnostics import Diagnostic
    from ontobq.orchestrate.plan import DeploymentPlan, PlanArtifact, ValidationSummary
    from ontobq.orchestrate.validate import ValidationResult


def format_diagnostic(diagnostic: Diagnostic) -> str:
    """Frozen human line: ``error OBQ102 path: message``."""

    return f"{diagnostic.severity.value} {diagnostic.code} {diagnostic.path}: {diagnostic.message}"


def diagnostic_payload(diagnostic: Diagnostic) -> dict[str, object]:
    """Machine-readable diagnostic object for CLI JSON."""

    return {
        "code": diagnostic.code,
        "severity": diagnostic.severity.value,
        "path": diagnostic.path,
        "message": diagnostic.message,
        "evidence": list(diagnostic.evidence),
    }


def validation_payload(result: ValidationResult) -> dict[str, object]:
    """JSON object for ``ontobq validate --format json``."""

    return {
        "ok": not result.has_errors,
        "layers_run": list(result.layers_run),
        "diagnostics": [diagnostic_payload(item) for item in result.diagnostics],
        "offline_only": result.offline_only,
        "include_integrity": result.include_integrity,
    }


def _bool_text(value: bool) -> str:
    if value:
        return "true"
    return "false"


def _summary_lines(summary: ValidationSummary) -> tuple[str, ...]:
    return (
        f"layers {','.join(summary.layers_run)}",
        f"errors {summary.error_count} warnings {summary.warning_count}",
        f"integrity_ran {_bool_text(summary.integrity_ran)}",
    )


def _artifact_line(index: int, artifact: PlanArtifact) -> str:
    return f"{index} {artifact.kind} {artifact.semantic_name} {artifact.target_name}"


def format_plan_human(plan: DeploymentPlan) -> str:
    """Identity, counts, numbered artifacts. No SQL."""

    identity = plan.domain_identity
    qualified = f"{identity.project}.{identity.dataset}.{identity.graph}"
    header = (f"plan {identity.name} {qualified}", *_summary_lines(plan.validation_summary))
    artifacts = tuple(
        _artifact_line(index, artifact) for index, artifact in enumerate(plan.artifacts, start=1)
    )
    return "\n".join((*header, *artifacts))


def _artifact_payload(artifact: PlanArtifact, include_sql: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": artifact.kind,
        "semantic_name": artifact.semantic_name,
        "target_name": artifact.target_name,
        "dependencies": list(artifact.dependencies),
        "content_hash": artifact.content_hash,
    }
    if include_sql:
        payload["sql"] = artifact.sql
    return payload


def _summary_payload(summary: ValidationSummary) -> dict[str, object]:
    return {
        "layers_run": list(summary.layers_run),
        "error_count": summary.error_count,
        "warning_count": summary.warning_count,
        "offline_only": summary.offline_only,
        "include_integrity": summary.include_integrity,
        "integrity_ran": summary.integrity_ran,
        "diagnostic_codes": list(summary.diagnostic_codes),
    }


def plan_payload(
    plan: DeploymentPlan,
    result: ValidationResult,
    *,
    include_sql: bool,
) -> dict[str, object]:
    """JSON object for ``ontobq plan --format json``."""

    identity = plan.domain_identity
    payload = validation_payload(result)
    payload["domain_identity"] = {
        "name": identity.name,
        "project": identity.project,
        "dataset": identity.dataset,
        "graph": identity.graph,
    }
    payload["validation_summary"] = _summary_payload(plan.validation_summary)
    payload["artifacts"] = [_artifact_payload(item, include_sql) for item in plan.artifacts]
    return payload


def dumps_json(payload: dict[str, object]) -> str:
    """Stable pretty JSON with sorted keys."""

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def format_validation_human(result: ValidationResult) -> str:
    """One frozen diagnostic line per finding. Empty when there are none."""

    if not result.diagnostics:
        return ""
    return "\n".join(format_diagnostic(item) for item in result.diagnostics) + "\n"


def concatenated_sql(plan: DeploymentPlan) -> str:
    """Artifact SQL in DAG order, each statement newline-terminated, blank-line separated."""

    chunks: list[str] = []
    for artifact in plan.artifacts:
        sql = artifact.sql if artifact.sql.endswith("\n") else f"{artifact.sql}\n"
        chunks.append(sql)
    return "\n".join(chunks)


def unqualified_target(target_name: str) -> str:
    """Last dotted segment of a fully-qualified BigQuery name."""

    return target_name.rsplit(".", 1)[-1]


def write_sql_directory(plan: DeploymentPlan, directory: Path) -> None:
    """Write one ``.sql`` file per artifact named from the unqualified target."""

    directory.mkdir(parents=True, exist_ok=True)
    for artifact in plan.artifacts:
        sql = artifact.sql if artifact.sql.endswith("\n") else f"{artifact.sql}\n"
        (directory / f"{unqualified_target(artifact.target_name)}.sql").write_text(
            sql, encoding="utf-8"
        )
