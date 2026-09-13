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

"""Cost-aware Domain validation: load, semantics, metadata, then integrity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ontobq.diagnostics import Diagnostic, DomainLoadError, Severity
from ontobq.ir import Domain
from ontobq.load import load_domain
from ontobq.semantics import validate_semantics
from ontobq.validate import IntegrityExecutionError, validate_bigquery_metadata, validate_integrity

if TYPE_CHECKING:
    from pathlib import Path

    from ontobq.bigquery.inspector import BigQueryInspector
    from ontobq.bq.executor import BigQueryReadExecutor

LAYER_LOAD = "load"
LAYER_SEMANTICS = "semantics"
LAYER_METADATA = "metadata"
LAYER_INTEGRITY = "integrity"
USAGE_CODE = "USAGE"


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of ``validate_domain``. ``include_integrity`` is the requested policy."""

    domain: Domain | None
    diagnostics: tuple[Diagnostic, ...]
    layers_run: tuple[str, ...]
    offline_only: bool
    include_integrity: bool

    @property
    def has_errors(self) -> bool:
        """True when any diagnostic is ``Severity.ERROR``."""

        return any(item.severity is Severity.ERROR for item in self.diagnostics)


@dataclass(frozen=True)
class _Request:
    source: str | Path | Domain
    inspector: BigQueryInspector | None
    query_executor: BigQueryReadExecutor | None
    offline_only: bool
    include_integrity: bool


@dataclass(frozen=True)
class _State:
    domain: Domain | None
    diagnostics: tuple[Diagnostic, ...]
    layers_run: tuple[str, ...]
    request: _Request

    @property
    def has_errors(self) -> bool:
        return any(item.severity is Severity.ERROR for item in self.diagnostics)


def validate_domain(
    source: str | Path | Domain,
    *,
    inspector: BigQueryInspector | None = None,
    query_executor: BigQueryReadExecutor | None = None,
    offline_only: bool = False,
    include_integrity: bool = True,
) -> ValidationResult:
    """Run validation layers in cost-aware order. Never mutates BigQuery."""

    request = _Request(source, inspector, query_executor, offline_only, include_integrity)
    return _result_from_state(_run_layers(_load_state(request)))


def _usage(message: str) -> Diagnostic:
    return Diagnostic(
        code=USAGE_CODE, severity=Severity.ERROR, path="orchestration", message=message
    )


def _result_from_state(state: _State) -> ValidationResult:
    return ValidationResult(
        domain=state.domain,
        diagnostics=state.diagnostics,
        layers_run=state.layers_run,
        offline_only=state.request.offline_only,
        include_integrity=state.request.include_integrity,
    )


def _with_diagnostics(state: _State, extra: tuple[Diagnostic, ...]) -> _State:
    return _State(
        domain=state.domain,
        diagnostics=state.diagnostics + extra,
        layers_run=state.layers_run,
        request=state.request,
    )


def _append_layer(state: _State, layer: str, extra: tuple[Diagnostic, ...]) -> _State:
    labeled = _with_diagnostics(state, extra)
    return _State(
        domain=labeled.domain,
        diagnostics=labeled.diagnostics,
        layers_run=(*state.layers_run, layer),
        request=state.request,
    )


def _load_state(request: _Request) -> _State:
    source = request.source
    if isinstance(source, Domain):
        return _State(domain=source, diagnostics=(), layers_run=(), request=request)
    try:
        domain = load_domain(source)
    except DomainLoadError as error:
        return _State(
            domain=None,
            diagnostics=error.diagnostics,
            layers_run=(LAYER_LOAD,),
            request=request,
        )
    return _State(domain=domain, diagnostics=(), layers_run=(LAYER_LOAD,), request=request)


def _run_layers(state: _State) -> _State:
    if state.domain is None:
        return state
    after_semantics = _semantics_layer(state)
    after_metadata = _metadata_layer(after_semantics)
    return _integrity_layer(after_metadata)


def _semantics_layer(state: _State) -> _State:
    if state.domain is None:
        return state
    return _append_layer(state, LAYER_SEMANTICS, validate_semantics(state.domain))


def _metadata_layer(state: _State) -> _State:
    if state.request.offline_only or state.has_errors or state.domain is None:
        return state
    inspector = state.request.inspector
    if inspector is None:
        return _with_diagnostics(
            state,
            (_usage("BigQuery inspector is required unless offline-only validation is requested"),),
        )
    return _append_layer(state, LAYER_METADATA, validate_bigquery_metadata(state.domain, inspector))


def _should_run_integrity(state: _State) -> bool:
    request = state.request
    return (
        not request.offline_only
        and request.include_integrity
        and not state.has_errors
        and state.domain is not None
    )


def _integrity_layer(state: _State) -> _State:
    domain = state.domain
    executor = state.request.query_executor
    if not _should_run_integrity(state) or domain is None:
        return state
    if executor is None:
        return _with_diagnostics(
            state,
            (
                _usage(
                    "BigQuery query executor is required unless offline-only or integrity "
                    "checks are skipped"
                ),
            ),
        )
    return _append_layer(state, LAYER_INTEGRITY, _integrity_diagnostics(domain, executor))


def _integrity_diagnostics(
    domain: Domain,
    executor: BigQueryReadExecutor,
) -> tuple[Diagnostic, ...]:
    try:
        report = validate_integrity(domain, executor)
    except IntegrityExecutionError as error:
        return (
            Diagnostic(
                code=USAGE_CODE,
                severity=Severity.ERROR,
                path=error.query.path,
                message=str(error),
                evidence=(error.query.code, error.query.element),
            ),
        )
    return report.diagnostics
