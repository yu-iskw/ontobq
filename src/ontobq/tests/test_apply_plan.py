"""apply_plan against real #15 plans and FakeMutationExecutor. No mocks."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from ontobq.bq.mutator import MutationIdentity, MutationReceipt
from ontobq.cli import main
from ontobq.orchestrate.apply import apply_plan
from ontobq.orchestrate.plan import build_plan
from ontobq.orchestrate.render import format_apply_human
from ontobq.tests.fakes.executor import FakeMutationExecutor
from ontobq.tests.orchestrate_support import clean_executor, commerce_inspector
from ontobq.tests.paths import FIXTURES_DIR

if TYPE_CHECKING:
    import pytest  # pyright: ignore[reportMissingImports]

_COMMERCE = FIXTURES_DIR / "commerce.yaml"
_SEMANTIC_INVALID = FIXTURES_DIR / "semantics" / "obq001-unknown-key-property.yaml"


def _plan_commerce():
    return build_plan(_COMMERCE, inspector=commerce_inspector(), query_executor=clean_executor())


def _offline_plan():
    return build_plan(_COMMERCE, offline_only=True)


def test_commerce_apply_submits_views_before_graph_verbatim() -> None:
    plan = _plan_commerce()
    fake = FakeMutationExecutor()
    result = apply_plan(plan, fake)
    assert result.ok
    assert not result.refused
    kinds = tuple(item.kind for item in result.artifacts)
    assert kinds == ("mapping_view", "mapping_view", "mapping_view", "property_graph")
    assert tuple(item.status for item in result.artifacts) == ("applied",) * 4
    submitted_sql = tuple(sql for _, sql in fake.submitted)
    assert submitted_sql == tuple(item.sql for item in plan.artifacts)
    assert tuple(name for name, _ in fake.submitted) == tuple(
        item.target_name for item in plan.artifacts
    )


def test_second_apply_same_plan_is_unchanged_and_adds_no_targets() -> None:
    plan = _plan_commerce()
    fake = FakeMutationExecutor()
    first = apply_plan(plan, fake)
    second = apply_plan(plan, fake)
    assert first.ok and second.ok
    assert tuple(item.status for item in second.artifacts) == ("unchanged",) * 4
    targets = [name for name, _ in fake.submitted]
    expected = [item.target_name for item in plan.artifacts]
    assert targets == expected + expected
    assert set(fake.definitions) == set(expected)


def test_error_level_diagnostics_refuse_without_execute() -> None:
    plan = _plan_commerce()
    summary = replace(plan.validation_summary, error_count=1)
    blocked = replace(plan, validation_summary=summary)
    fake = FakeMutationExecutor()
    result = apply_plan(blocked, fake)
    assert result.refused
    assert "plan has error-level diagnostics" in result.refusal_reasons
    assert fake.submitted == []
    assert all(item.status == "skipped" for item in result.artifacts)


def test_integrity_not_ran_refuses_by_default() -> None:
    plan = _offline_plan()
    assert plan.validation_summary.integrity_ran is False
    fake = FakeMutationExecutor()
    result = apply_plan(plan, fake)
    assert result.refused
    assert "integrity did not run" in result.refusal_reasons
    assert fake.submitted == []


def test_integrity_not_ran_allowed_when_require_integrity_false() -> None:
    plan = _offline_plan()
    fake = FakeMutationExecutor()
    result = apply_plan(plan, fake, require_integrity=False)
    assert result.ok
    assert len(fake.submitted) == len(plan.artifacts)


def test_tampered_sql_hash_mismatch_refuses() -> None:
    plan = _plan_commerce()
    first = plan.artifacts[0]
    tampered = replace(first, sql=first.sql + "\n-- tampered")
    blocked = replace(plan, artifacts=(tampered, *plan.artifacts[1:]))
    fake = FakeMutationExecutor()
    result = apply_plan(blocked, fake)
    assert result.refused
    assert any("hash mismatch" in reason for reason in result.refusal_reasons)
    assert fake.submitted == []


def test_executor_identity_mismatch_refuses() -> None:
    plan = _plan_commerce()
    fake = FakeMutationExecutor(project="other-project")
    result = apply_plan(plan, fake)
    assert result.refused
    assert "executor identity does not match plan domain" in result.refusal_reasons
    assert fake.submitted == []


def test_unresolved_dependency_refuses() -> None:
    plan = _plan_commerce()
    graph = replace(plan.artifacts[-1], dependencies=("missing.view",))
    blocked = replace(plan, artifacts=(*plan.artifacts[:-1], graph))
    fake = FakeMutationExecutor()
    result = apply_plan(blocked, fake)
    assert result.refused
    assert any("unresolved dependency" in reason for reason in result.refusal_reasons)
    assert fake.submitted == []


def test_graph_before_views_refuses() -> None:
    plan = _plan_commerce()
    blocked = replace(plan, artifacts=(plan.artifacts[-1], *plan.artifacts[:-1]))
    fake = FakeMutationExecutor()
    result = apply_plan(blocked, fake)
    assert result.refused
    assert "property graph is not last" in result.refusal_reasons
    assert fake.submitted == []


def test_fail_on_first_view_skips_remaining_and_graph() -> None:
    plan = _plan_commerce()
    first = plan.artifacts[0].target_name
    fake = FakeMutationExecutor(fail_at_target=first)
    result = apply_plan(plan, fake)
    assert not result.ok
    assert not result.refused
    statuses = tuple(item.status for item in result.artifacts)
    assert statuses[0] == "failed"
    assert statuses[1:] == ("skipped",) * (len(plan.artifacts) - 1)
    assert result.artifacts[0].error == "injected failure"
    assert fake.submitted == [(first, plan.artifacts[0].sql)]


def test_fail_on_graph_after_views_applied() -> None:
    plan = _plan_commerce()
    graph = plan.artifacts[-1].target_name
    fake = FakeMutationExecutor(fail_at_target=graph)
    result = apply_plan(plan, fake)
    views = result.artifacts[:-1]
    last = result.artifacts[-1]
    assert all(item.status == "applied" for item in views)
    assert last.status == "failed"
    assert last.kind == "property_graph"
    assert tuple(name for name, _ in fake.submitted) == tuple(
        item.target_name for item in plan.artifacts
    )


def test_apply_cli_semantic_invalid_is_nonzero_without_mutation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = FakeMutationExecutor()
    code = main(
        ["apply", str(_SEMANTIC_INVALID)],
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
        mutator=fake,
    )
    output = capsys.readouterr().out
    assert code == 1
    assert fake.submitted == []
    assert "OBQ001" in output


def test_apply_cli_commerce_success(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeMutationExecutor()
    code = main(
        ["apply", "--format", "json", str(_COMMERCE)],
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
        mutator=fake,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["refused"] is False
    assert [item["status"] for item in payload["artifacts"]] == ["applied"] * 4
    assert len(fake.submitted) == 4


def test_apply_does_not_write_state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    plan = _plan_commerce()
    apply_plan(plan, FakeMutationExecutor())
    leftover = [path.name for path in tmp_path.iterdir() if path.name != "home"]
    assert leftover == []
    assert not (home / ".ontobq").exists()
    assert list(home.iterdir()) == []


def test_empty_sql_refuses() -> None:
    plan = _plan_commerce()
    blank = replace(plan.artifacts[0], sql="")
    blocked = replace(plan, artifacts=(blank, *plan.artifacts[1:]))
    fake = FakeMutationExecutor()
    result = apply_plan(blocked, fake)
    assert result.refused
    assert any("empty kind or sql" in reason for reason in result.refusal_reasons)
    assert fake.submitted == []


def test_duplicate_target_name_refuses() -> None:
    plan = _plan_commerce()
    first = plan.artifacts[0]
    duplicate = replace(plan.artifacts[1], target_name=first.target_name)
    blocked = replace(plan, artifacts=(first, duplicate, *plan.artifacts[2:]))
    fake = FakeMutationExecutor()
    result = apply_plan(blocked, fake)
    assert result.refused
    assert any("duplicate target_name" in reason for reason in result.refusal_reasons)
    assert fake.submitted == []


def test_missing_graph_refuses() -> None:
    plan = _plan_commerce()
    blocked = replace(plan, artifacts=plan.artifacts[:-1])
    fake = FakeMutationExecutor()
    result = apply_plan(blocked, fake)
    assert result.refused
    assert "property graph is missing" in result.refusal_reasons
    assert fake.submitted == []


def test_empty_kind_refuses() -> None:
    plan = _plan_commerce()
    blank = replace(plan.artifacts[0], kind=cast("str", ""))
    blocked = replace(plan, artifacts=(blank, *plan.artifacts[1:]))
    fake = FakeMutationExecutor()
    result = apply_plan(blocked, fake)
    assert result.refused
    assert fake.submitted == []


def test_empty_artifacts_refuses() -> None:
    plan = replace(_plan_commerce(), artifacts=())
    fake = FakeMutationExecutor()
    result = apply_plan(plan, fake)
    assert result.refused
    assert "plan has no artifacts" in result.refusal_reasons
    assert result.ok is False
    assert fake.submitted == []


class _RaisingExecutor:
    """Duck-typed executor that raises. Not a mock library patch."""

    def __init__(self) -> None:
        self._identity = FakeMutationExecutor().identity

    @property
    def identity(self) -> MutationIdentity:
        return self._identity

    def execute_ddl(self, sql: str, *, target_name: str) -> MutationReceipt:
        del sql, target_name
        raise RuntimeError("boom")


def test_execute_ddl_exception_marks_failed_and_skips_rest() -> None:
    plan = _plan_commerce()
    result = apply_plan(plan, _RaisingExecutor())
    assert not result.ok
    assert result.artifacts[0].status == "failed"
    assert result.artifacts[0].error == "boom"
    assert all(item.status == "skipped" for item in result.artifacts[1:])


def test_apply_cli_human_refuse_and_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = FakeMutationExecutor()
    code = main(
        ["apply", "--format", "human", str(_SEMANTIC_INVALID)],
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
        mutator=fake,
    )
    assert code == 1
    assert "OBQ001" in capsys.readouterr().out
    plan = _plan_commerce()
    failing = FakeMutationExecutor(fail_at_target=plan.artifacts[0].target_name)
    code = main(
        ["apply", "--format", "human", str(_COMMERCE)],
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
        mutator=failing,
    )
    output = capsys.readouterr().out
    assert code == 1
    assert "failed injected failure" in output
    assert "skipped" in output


def test_refused_apply_human_render() -> None:
    plan = _plan_commerce()
    blocked = replace(plan, validation_summary=replace(plan.validation_summary, error_count=1))
    result = apply_plan(blocked, FakeMutationExecutor())
    text = format_apply_human(result)
    assert text.startswith("apply refused")
    assert "plan has error-level diagnostics" in text
