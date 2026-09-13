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

"""Apply a frozen DeploymentPlan. Never compiles SQL or re-runs validators."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ontobq.bq.mutator import MutationExecutor, MutationReceipt
    from ontobq.orchestrate.plan import DeploymentPlan, PlanArtifact

ApplyStatus = Literal["applied", "unchanged", "failed", "skipped"]


@dataclass(frozen=True)
class ArtifactApplyStatus:
    """Per-artifact mutation outcome. Order matches the plan."""

    target_name: str
    kind: str
    semantic_name: str
    status: ApplyStatus
    job_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ApplyResult:
    """Public apply outcome. Safety-gate failures set ``refused=True`` (no exception)."""

    refused: bool
    refusal_reasons: tuple[str, ...]
    artifacts: tuple[ArtifactApplyStatus, ...]

    @property
    def ok(self) -> bool:
        """True when nothing was refused and every artifact applied or was unchanged."""

        if self.refused:
            return False
        return all(item.status in {"applied", "unchanged"} for item in self.artifacts)


def apply_plan(
    plan: DeploymentPlan,
    executor: MutationExecutor,
    *,
    require_integrity: bool = True,
) -> ApplyResult:
    """Execute plan SQL verbatim in artifact order, or refuse before any mutation."""

    reasons = _refusal_reasons(plan, executor, require_integrity)
    if reasons:
        return _refused_result(plan, reasons)
    return _execute(plan, executor)


def _sql_hash(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _refusal_reasons(
    plan: DeploymentPlan,
    executor: MutationExecutor,
    require_integrity: bool,
) -> tuple[str, ...]:
    return (
        *_error_reasons(plan),
        *_integrity_reasons(plan, require_integrity),
        *_structure_reasons(plan),
        *_identity_reasons(plan, executor),
        *_hash_reasons(plan),
    )


def _error_reasons(plan: DeploymentPlan) -> tuple[str, ...]:
    if plan.validation_summary.error_count > 0:
        return ("plan has error-level diagnostics",)
    return ()


def _integrity_reasons(plan: DeploymentPlan, require_integrity: bool) -> tuple[str, ...]:
    if require_integrity and not plan.validation_summary.integrity_ran:
        return ("integrity did not run",)
    return ()


def _identity_reasons(plan: DeploymentPlan, executor: MutationExecutor) -> tuple[str, ...]:
    expected = plan.domain_identity
    got = executor.identity
    if got.project != expected.project or got.dataset != expected.dataset:
        return ("executor identity does not match plan domain",)
    return ()


def _hash_reasons(plan: DeploymentPlan) -> tuple[str, ...]:
    reasons: list[str] = []
    for artifact in plan.artifacts:
        if _sql_hash(artifact.sql) != artifact.content_hash:
            reasons.append(f"artifact hash mismatch: {artifact.target_name}")
    return tuple(reasons)


def _structure_reasons(plan: DeploymentPlan) -> tuple[str, ...]:
    artifacts = plan.artifacts
    if not artifacts:
        return ("plan has no artifacts",)
    return (
        *_empty_field_reasons(artifacts),
        *_duplicate_reasons(artifacts),
        *_order_reasons(artifacts),
        *_dependency_reasons(artifacts),
    )


def _empty_field_reasons(artifacts: tuple[PlanArtifact, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    for artifact in artifacts:
        if not artifact.kind or not artifact.sql:
            reasons.append(f"empty kind or sql: {artifact.target_name}")
    return tuple(reasons)


def _duplicate_reasons(artifacts: tuple[PlanArtifact, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    reasons: list[str] = []
    for artifact in artifacts:
        name = artifact.target_name
        if name in seen:
            reasons.append(f"duplicate target_name: {name}")
        seen.add(name)
    return tuple(reasons)


def _order_reasons(artifacts: tuple[PlanArtifact, ...]) -> tuple[str, ...]:
    kinds = tuple(item.kind for item in artifacts)
    if "property_graph" not in kinds:
        return ("property graph is missing",)
    if kinds[-1] != "property_graph":
        return ("property graph is not last",)
    if any(kind != "mapping_view" for kind in kinds[:-1]):
        return ("mapping views must precede the property graph",)
    return ()


def _dependency_reasons(artifacts: tuple[PlanArtifact, ...]) -> tuple[str, ...]:
    known = {item.target_name for item in artifacts}
    reasons: list[str] = []
    for artifact in artifacts:
        for dep in artifact.dependencies:
            if dep not in known:
                reasons.append(f"unresolved dependency {dep} on {artifact.target_name}")
    return tuple(reasons)


def _refused_result(plan: DeploymentPlan, reasons: tuple[str, ...]) -> ApplyResult:
    skipped = tuple(_status(item, "skipped") for item in plan.artifacts)
    return ApplyResult(refused=True, refusal_reasons=reasons, artifacts=skipped)


def _execute(plan: DeploymentPlan, executor: MutationExecutor) -> ApplyResult:
    statuses: list[ArtifactApplyStatus] = []
    failed = False
    for artifact in plan.artifacts:
        if failed:
            statuses.append(_status(artifact, "skipped"))
            continue
        status = _run_one(executor, artifact)
        statuses.append(status)
        if status.status == "failed":
            failed = True
    return ApplyResult(refused=False, refusal_reasons=(), artifacts=tuple(statuses))


def _run_one(executor: MutationExecutor, artifact: PlanArtifact) -> ArtifactApplyStatus:
    try:
        receipt = executor.execute_ddl(artifact.sql, target_name=artifact.target_name)
    except Exception as error:  # noqa: BLE001 - executor surface is duck-typed
        return _status(artifact, "failed", error=str(error))
    return _from_receipt(artifact, receipt)


def _from_receipt(artifact: PlanArtifact, receipt: MutationReceipt) -> ArtifactApplyStatus:
    if not receipt.ok:
        return _status(artifact, "failed", job_id=receipt.job_id, error=receipt.error)
    if receipt.unchanged:
        return _status(artifact, "unchanged", job_id=receipt.job_id)
    return _status(artifact, "applied", job_id=receipt.job_id)


def _status(
    artifact: PlanArtifact,
    status: ApplyStatus,
    *,
    job_id: str | None = None,
    error: str | None = None,
) -> ArtifactApplyStatus:
    return ArtifactApplyStatus(
        target_name=artifact.target_name,
        kind=artifact.kind,
        semantic_name=artifact.semantic_name,
        status=status,
        job_id=job_id,
        error=error,
    )
