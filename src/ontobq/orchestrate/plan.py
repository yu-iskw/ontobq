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

"""Immutable deployment plan: mapping views then one property graph. Read-only."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ontobq.compile import compile_mapping_views, compile_property_graph
from ontobq.diagnostics import DomainLoadError, Severity
from ontobq.ir import Domain
from ontobq.load import load_domain
from ontobq.orchestrate.validate import LAYER_INTEGRITY, ValidationResult, validate_domain

if TYPE_CHECKING:
    from pathlib import Path

    from ontobq.bigquery.inspector import BigQueryInspector
    from ontobq.bq.executor import BigQueryReadExecutor
    from ontobq.compile.mapping_views import MappingViewArtifact
    from ontobq.compile.property_graph import PropertyGraphArtifact


@dataclass(frozen=True)
class DomainIdentity:
    """Stable Domain coordinates used by plan and later apply."""

    name: str
    project: str
    dataset: str
    graph: str


@dataclass(frozen=True)
class ValidationSummary:
    """Plan-facing validation snapshot. ``integrity_ran`` false is not apply-safe."""

    layers_run: tuple[str, ...]
    error_count: int
    warning_count: int
    offline_only: bool
    include_integrity: bool
    integrity_ran: bool
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True)
class PlanArtifact:
    """One deployment unit. ``sql`` is opaque compiler output; ``content_hash`` is SHA-256."""

    kind: Literal["mapping_view", "property_graph"]
    semantic_name: str
    target_name: str
    sql: str
    dependencies: tuple[str, ...]
    content_hash: str


@dataclass(frozen=True)
class DeploymentPlan:
    """Frozen artifact DAG. Identical IR and compiler output yield an identical plan."""

    domain_identity: DomainIdentity
    validation_summary: ValidationSummary
    artifacts: tuple[PlanArtifact, ...]


class PlanBlockedError(Exception):
    """Raised when ``build_plan`` refuses to compile because validation has errors."""

    def __init__(self, validation: ValidationResult) -> None:
        self.validation = validation
        super().__init__("plan blocked by error-level diagnostics")


@dataclass(frozen=True)
class _PlanCall:
    source: str | Path | Domain
    inspector: BigQueryInspector | None
    query_executor: BigQueryReadExecutor | None
    offline_only: bool
    include_integrity: bool
    validation: ValidationResult | None


def build_plan(  # noqa: PLR0913
    source: str | Path | Domain,
    *,
    inspector: BigQueryInspector | None = None,
    query_executor: BigQueryReadExecutor | None = None,
    offline_only: bool = False,
    include_integrity: bool = True,
    validation: ValidationResult | None = None,
) -> DeploymentPlan:
    """Compile mapping views then the property graph after a clean validation."""

    result = _resolve_validation(
        _PlanCall(
            source,
            inspector,
            query_executor,
            offline_only,
            include_integrity,
            validation,
        )
    )
    if result.has_errors or result.domain is None:
        raise PlanBlockedError(result)
    return _assemble_plan(result)


def _resolve_validation(call: _PlanCall) -> ValidationResult:
    if call.validation is not None and _reusable(
        call.validation, call.source, call.offline_only, call.include_integrity
    ):
        return call.validation
    return validate_domain(
        call.source,
        inspector=call.inspector,
        query_executor=call.query_executor,
        offline_only=call.offline_only,
        include_integrity=call.include_integrity,
    )


def _reusable(
    validation: ValidationResult,
    source: str | Path | Domain,
    offline_only: bool,
    include_integrity: bool,
) -> bool:
    domain = validation.domain
    loaded = _domain_from_source(source)
    if domain is None or loaded is None:
        return False
    if validation.offline_only != offline_only or validation.include_integrity != include_integrity:
        return False
    return domain == loaded


def _domain_from_source(source: str | Path | Domain) -> Domain | None:
    if isinstance(source, Domain):
        return source
    try:
        return load_domain(source)
    except DomainLoadError:
        return None


def _identity(domain: Domain) -> DomainIdentity:
    target = domain.bigquery
    return DomainIdentity(
        name=domain.metadata.name,
        project=target.project,
        dataset=target.dataset,
        graph=target.graph,
    )


def _summary(result: ValidationResult) -> ValidationSummary:
    diagnostics = result.diagnostics
    return ValidationSummary(
        layers_run=result.layers_run,
        error_count=sum(item.severity is Severity.ERROR for item in diagnostics),
        warning_count=sum(item.severity is Severity.WARNING for item in diagnostics),
        offline_only=result.offline_only,
        include_integrity=result.include_integrity,
        integrity_ran=LAYER_INTEGRITY in result.layers_run,
        diagnostic_codes=tuple(item.code for item in diagnostics),
    )


def _sql_hash(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _mapping_artifact(view: MappingViewArtifact) -> PlanArtifact:
    return PlanArtifact(
        kind="mapping_view",
        semantic_name=view.semantic_name,
        target_name=view.qualified_name,
        sql=view.sql,
        dependencies=(),
        content_hash=_sql_hash(view.sql),
    )


def _graph_artifact(graph: PropertyGraphArtifact, view_targets: tuple[str, ...]) -> PlanArtifact:
    return PlanArtifact(
        kind="property_graph",
        semantic_name=graph.semantic_name,
        target_name=graph.qualified_name,
        sql=graph.sql,
        dependencies=view_targets,
        content_hash=_sql_hash(graph.sql),
    )


def _assemble_plan(result: ValidationResult) -> DeploymentPlan:
    domain = result.domain
    if domain is None:
        raise PlanBlockedError(result)
    views = compile_mapping_views(domain)
    graph = compile_property_graph(domain, views)
    mapping_items = tuple(_mapping_artifact(view) for view in views)
    view_targets = tuple(item.target_name for item in mapping_items)
    artifacts = (*mapping_items, _graph_artifact(graph, view_targets))
    return DeploymentPlan(
        domain_identity=_identity(domain),
        validation_summary=_summary(result),
        artifacts=artifacts,
    )
