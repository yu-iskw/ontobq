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
from ontobq.tests.e2e.templates import substitute_tokens


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


def test_exact_and_prefix_allowlist() -> None:
    assert project_is_allowed("ontobq-e2e-ci", "ontobq-e2e-ci,other")
    assert project_is_allowed("ontobq-e2e-ci", "ontobq-e2e-*")
    assert not project_is_allowed("prod", "ontobq-e2e-*")


def test_enabled_when_gates_pass() -> None:
    decision = decide_e2e(
        {
            ENABLE_ENV: "1",
            PROJECT_ENV: "ontobq-e2e-ci",
            DATASET_ENV: "e2e_scratch",
            ALLOWED_ENV: "ontobq-e2e-*",
        }
    )
    assert decision.enabled
    assert decision.project == "ontobq-e2e-ci"
    assert decision.dataset == "e2e_scratch"
    assert decision.graph == "commerce_e2e_graph"


def test_substitute_refuses_rfc_project() -> None:
    with pytest.raises(ValueError, match="my-project"):
        substitute_tokens("project: my-project", "safe-proj", "ds")
