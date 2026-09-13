"""Plan determinism: identical catalog input yields stable artifacts and apply order."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ontobq import apply_plan, build_plan
from ontobq.tests.e2e.recording import RecordingMutationExecutor

if TYPE_CHECKING:
    from ontobq.orchestrate.plan import DeploymentPlan
    from ontobq.tests.e2e.conftest import LiveE2E


def _plan(live: LiveE2E) -> DeploymentPlan:
    return build_plan(
        live.domain_path,
        inspector=live.inspector,
        query_executor=live.query_executor,
    )


def _fingerprints(plan: DeploymentPlan) -> tuple[tuple[str, str, str, str, str], ...]:
    return tuple(
        (
            item.kind,
            item.semantic_name,
            item.target_name,
            item.content_hash,
            item.sql,
        )
        for item in plan.artifacts
    )


def test_two_plans_match_byte_for_byte(e2e_live: LiveE2E) -> None:
    first = _plan(e2e_live)
    second = _plan(e2e_live)
    assert _fingerprints(first) == _fingerprints(second)
    assert tuple(item.dependencies for item in first.artifacts) == tuple(
        item.dependencies for item in second.artifacts
    )


def test_plan_after_apply_equals_plan_before_unchanged_domain(e2e_live: LiveE2E) -> None:
    before = _fingerprints(_plan(e2e_live))
    apply_plan(_plan(e2e_live), e2e_live.mutator)
    after = _fingerprints(_plan(e2e_live))
    assert before == after


def test_apply_order_matches_plan_order(e2e_live: LiveE2E) -> None:
    plan = _plan(e2e_live)
    recording = RecordingMutationExecutor(e2e_live.mutator)
    result = apply_plan(plan, recording)
    assert result.ok
    assert tuple(name for name, _ in recording.calls) == tuple(
        item.target_name for item in plan.artifacts
    )
    assert tuple(item.kind for item in plan.artifacts)[-1] == "property_graph"
    assert all(item.kind == "mapping_view" for item in plan.artifacts[:-1])
