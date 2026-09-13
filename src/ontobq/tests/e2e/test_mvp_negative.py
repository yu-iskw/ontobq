"""Negative MVP cases fail before mutation with exact Diagnostic.code values."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest  # pyright: ignore[reportMissingImports]

from ontobq.cli import main
from ontobq.orchestrate.plan import PlanBlockedError, build_plan
from ontobq.tests.e2e.recording import RecordingMutationExecutor
from ontobq.tests.e2e.templates import NEGATIVE_FILES, materialize_file

if TYPE_CHECKING:
    from pathlib import Path

    from ontobq.tests.e2e.conftest import LiveE2E


def _variant_path(live: LiveE2E, filename: str) -> Path:
    return materialize_file(
        filename,
        live.workdir / filename,
        live.project,
        live.dataset,
        live.graph,
    )


def _validate_codes(
    live: LiveE2E,
    path: Path,
    capsys: pytest.CaptureFixture[str],
) -> list[str]:
    code = main(
        ["validate", "--format", "json", str(path)],
        inspector=live.inspector,
        query_executor=live.query_executor,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["ok"] is False
    return [item["code"] for item in payload["diagnostics"]]


def _assert_apply_not_invoked(live: LiveE2E, path: Path) -> None:
    recording = RecordingMutationExecutor(live.mutator)
    with pytest.raises(PlanBlockedError):
        build_plan(
            path,
            inspector=live.inspector,
            query_executor=live.query_executor,
        )
    code = main(
        ["apply", "--format", "json", str(path)],
        inspector=live.inspector,
        query_executor=live.query_executor,
        mutator=recording,
    )
    assert code == 1
    assert not recording.calls


@pytest.mark.parametrize(("expected", "filename"), NEGATIVE_FILES)
def test_negative_code_blocks_apply(
    e2e_live: LiveE2E,
    expected: str,
    filename: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _variant_path(e2e_live, filename)
    codes = _validate_codes(e2e_live, path, capsys)
    assert expected in codes
    _assert_apply_not_invoked(e2e_live, path)
