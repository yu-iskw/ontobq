"""Offline E2E allowlist gates. No BigQuery client, no DDL."""

from __future__ import annotations

import pytest  # pyright: ignore[reportMissingImports]

from ontobq.tests.e2e.gates import (
    ALLOWED_ENV,
    DATASET_ENV,
    ENABLE_ENV,
    PROJECT_ENV,
    decide_e2e,
    project_is_allowed,
)
from ontobq.tests.e2e.templates import RunCoordinates, substitute_tokens


def test_enable_flag_off_skips() -> None:
    decision = decide_e2e({})
    assert not decision.enabled
    assert ENABLE_ENV in decision.reason


def test_missing_project_or_dataset_skips() -> None:
    decision = decide_e2e({ENABLE_ENV: "1", PROJECT_ENV: "demo-proj"})
    assert not decision.enabled


def test_unset_allowlist_refuses() -> None:
    decision = decide_e2e({ENABLE_ENV: "1", PROJECT_ENV: "demo-proj", DATASET_ENV: "e2e_ds"})
    assert not decision.enabled
    assert ALLOWED_ENV in decision.reason


def test_project_not_on_allowlist_refuses() -> None:
    decision = decide_e2e(
        {
            ENABLE_ENV: "1",
            PROJECT_ENV: "prod-proj",
            DATASET_ENV: "e2e_ds",
            ALLOWED_ENV: "ontobq-e2e-test,other-test",
        }
    )
    assert not decision.enabled
    assert "not in" in decision.reason


def test_rfc_fixture_project_refused_even_if_listed() -> None:
    decision = decide_e2e(
        {
            ENABLE_ENV: "1",
            PROJECT_ENV: "my-project",
            DATASET_ENV: "semantic",
            ALLOWED_ENV: "my-project",
        }
    )
    assert not decision.enabled
    assert "my-project" in decision.reason


def test_exact_allowlist_accepts_listed_projects() -> None:
    assert project_is_allowed("ontobq-e2e-ci", "ontobq-e2e-ci,other")
    assert not project_is_allowed("ontobq-e2e-ci-2", "ontobq-e2e-ci,other")


def test_wildcard_and_prefix_tokens_are_rejected() -> None:
    """No wildcard/prefix matching: ``*`` and ``prod*`` must not authorize a project family."""

    assert not project_is_allowed("anything", "*")
    assert not project_is_allowed("prod-123", "prod*")
    assert not project_is_allowed("ontobq-e2e-ci", "ontobq-e2e-*")
    assert not project_is_allowed("prod", "ontobq-e2e-*")


def test_enabled_when_gates_pass() -> None:
    decision = decide_e2e(
        {
            ENABLE_ENV: "1",
            PROJECT_ENV: "ontobq-e2e-ci",
            DATASET_ENV: "e2e_scratch",
            ALLOWED_ENV: "ontobq-e2e-ci",
        }
    )
    assert decision.enabled
    assert decision.project == "ontobq-e2e-ci"
    assert decision.dataset == "e2e_scratch"
    assert decision.graph == "commerce_e2e_graph"


def test_substitute_refuses_rfc_project() -> None:
    with pytest.raises(ValueError, match="my-project"):
        substitute_tokens("project: my-project", RunCoordinates(project="safe-proj", dataset="ds"))


def test_substitute_refuses_a_token_hidden_inside_a_coordinate_value() -> None:
    """A dataset (or project/graph/run_id) containing another token is rejected, not rewritten.

    Sequential ``str.replace`` calls would otherwise let a value inserted by
    an earlier replacement be recursively matched by a later one -- e.g. a
    dataset literally equal to ``${ONTOBQ_E2E_RUN_ID}`` would be silently
    turned into the generated run id instead of failing fast.
    """

    poisoned = RunCoordinates(
        project="safe-proj", dataset="${ONTOBQ_E2E_RUN_ID}", run_id="abcd1234"
    )
    with pytest.raises(ValueError, match="interpolation token"):
        substitute_tokens("dataset: ${ONTOBQ_E2E_DATASET}", poisoned)
