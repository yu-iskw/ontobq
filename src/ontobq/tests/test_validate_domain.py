"""validate_domain orchestration against real loaders/validators and Fake adapters."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import ontobq
from ontobq import (
    FakeBigQueryInspector,
    compile_integrity_queries,
    load_domain,
    validate_domain,
)
from ontobq.bq import FakeBigQueryReadExecutor
from ontobq.cli import main
from ontobq.diagnostics import Severity
from ontobq.orchestrate.validate import (
    LAYER_INTEGRITY,
    LAYER_LOAD,
    LAYER_METADATA,
    LAYER_SEMANTICS,
    USAGE_CODE,
    ValidationResult,
)
from ontobq.tests.orchestrate_support import (
    FailingExecutor,
    FailingInspector,
    catalog_without_country,
    clean_executor,
    commerce_inspector,
)
from ontobq.tests.paths import FIXTURES_DIR

if TYPE_CHECKING:
    import pytest  # pyright: ignore[reportMissingImports]

_COMMERCE = FIXTURES_DIR / "commerce.yaml"
_SEMANTICS = FIXTURES_DIR / "semantics"
_LAYERS_ALL = (LAYER_LOAD, LAYER_SEMANTICS, LAYER_METADATA, LAYER_INTEGRITY)
_LAYERS_OFFLINE = (LAYER_LOAD, LAYER_SEMANTICS)


def _codes(result: ValidationResult) -> tuple[str, ...]:
    return tuple(item.code for item in result.diagnostics)


def _validate_full(source: Path) -> ValidationResult:
    return validate_domain(source, inspector=commerce_inspector(), query_executor=clean_executor())


def test_commerce_happy_path_runs_layers_1_to_4() -> None:
    result = _validate_full(_COMMERCE)
    assert result.layers_run == _LAYERS_ALL
    assert result.domain is not None
    assert not result.has_errors
    assert result.offline_only is False
    assert result.include_integrity is True
    assert not result.diagnostics


def test_offline_runs_load_and_semantics_only() -> None:
    result = validate_domain(
        _COMMERCE,
        inspector=FailingInspector(),
        query_executor=FailingExecutor(),
        offline_only=True,
    )
    assert result.layers_run == _LAYERS_OFFLINE
    assert not result.has_errors
    assert result.offline_only is True


def test_semantic_error_skips_metadata_and_integrity() -> None:
    result = validate_domain(
        _SEMANTICS / "obq001-unknown-key-property.yaml",
        inspector=FailingInspector(),
        query_executor=FailingExecutor(),
    )
    assert result.layers_run == _LAYERS_OFFLINE
    assert result.has_errors
    assert "OBQ001" in _codes(result)
    assert LAYER_METADATA not in result.layers_run
    assert LAYER_INTEGRITY not in result.layers_run


def test_metadata_error_skips_integrity() -> None:
    result = validate_domain(
        _COMMERCE,
        inspector=FakeBigQueryInspector(catalog_without_country()),
        query_executor=FailingExecutor(),
    )
    assert result.layers_run == (LAYER_LOAD, LAYER_SEMANTICS, LAYER_METADATA)
    assert "OBQ102" in _codes(result)
    assert LAYER_INTEGRITY not in result.layers_run
    assert result.has_errors


def test_integrity_error_runs_all_layers() -> None:
    domain = load_domain(_COMMERCE)
    query = next(item for item in compile_integrity_queries(domain) if item.code == "OBQ201")
    executor = FakeBigQueryReadExecutor(
        {query.sql: ({"id": None, "violation_count": 1, "total_violations": 1},)}
    )
    result = validate_domain(_COMMERCE, inspector=commerce_inspector(), query_executor=executor)
    assert result.layers_run == _LAYERS_ALL
    assert "OBQ201" in _codes(result)
    assert result.has_errors


def test_skip_integrity_does_not_call_executor() -> None:
    result = validate_domain(
        _COMMERCE,
        inspector=commerce_inspector(),
        query_executor=FailingExecutor(),
        include_integrity=False,
    )
    assert result.layers_run == (LAYER_LOAD, LAYER_SEMANTICS, LAYER_METADATA)
    assert not result.has_errors
    assert result.include_integrity is False


def test_load_error_stops_before_semantics() -> None:
    result = validate_domain(FIXTURES_DIR / "invalid-kind.yaml", offline_only=True)
    assert result.layers_run == (LAYER_LOAD,)
    assert result.domain is None
    assert result.has_errors
    assert all(item.severity is Severity.ERROR for item in result.diagnostics)


def test_missing_inspector_is_usage_error() -> None:
    result = validate_domain(_COMMERCE, query_executor=clean_executor())
    assert USAGE_CODE in _codes(result)
    assert result.has_errors
    assert LAYER_METADATA not in result.layers_run


def test_missing_executor_is_usage_error() -> None:
    result = validate_domain(_COMMERCE, inspector=commerce_inspector())
    assert USAGE_CODE in _codes(result)
    assert LAYER_INTEGRITY not in result.layers_run


def test_already_loaded_domain_skips_load_layer() -> None:
    result = validate_domain(
        load_domain(_COMMERCE),
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
    )
    assert LAYER_LOAD not in result.layers_run
    assert result.layers_run == (LAYER_SEMANTICS, LAYER_METADATA, LAYER_INTEGRITY)


def test_validate_module_does_not_call_compilers() -> None:
    path = Path(ontobq.__file__).resolve().parent / "orchestrate" / "validate.py"
    parsed = ast.parse(path.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}
    assert "compile_mapping_views" not in names
    assert "compile_property_graph" not in names


def test_orchestrate_and_cli_stay_pure() -> None:
    root = Path(ontobq.__file__).resolve().parent
    paths = [root / "cli.py", *sorted((root / "orchestrate").glob("*.py"))]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "CREATE OR REPLACE" not in text
        assert "google.cloud" not in text
        assert "from google" not in text


def test_offline_cli_exits_zero_without_google(capsys: pytest.CaptureFixture[str]) -> None:
    before = {name for name in sys.modules if name.startswith("google.cloud")}
    code = main(["validate", "--offline", str(_COMMERCE)])
    after = {name for name in sys.modules if name.startswith("google.cloud")}
    assert code == 0
    assert after == before
    assert capsys.readouterr().out == ""


def test_semantic_error_cli_json_is_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    path = _SEMANTICS / "obq001-unknown-key-property.yaml"
    code = main(["validate", "--offline", "--format", "json", str(path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["ok"] is False
    assert payload["layers_run"] == ["load", "semantics"]
    assert payload["diagnostics"][0]["code"] == "OBQ001"
    assert payload["diagnostics"][0]["severity"] == "error"


def test_metadata_error_human_line_and_exit(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["validate", "--skip-integrity", "--format", "human", str(_COMMERCE)],
        inspector=FakeBigQueryInspector(catalog_without_country()),
        query_executor=FailingExecutor(),
    )
    output = capsys.readouterr().out
    assert code == 1
    assert output.startswith(
        "error OBQ102 spec.entities.Customer.mapping.bigquery.properties.country:"
    )


def test_happy_path_cli_json_ok(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["validate", "--format", "json", str(_COMMERCE)],
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["layers_run"] == list(_LAYERS_ALL)
    assert payload["diagnostics"] == []
