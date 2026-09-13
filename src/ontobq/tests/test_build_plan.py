"""build_plan orchestration against real compilers, Fake adapters, and goldens."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest  # pyright: ignore[reportMissingImports]

from ontobq import (
    FakeBigQueryInspector,
    compile_integrity_queries,
    compile_mapping_views,
    compile_property_graph,
    load_domain,
    validate_domain,
)
from ontobq.bq import FakeBigQueryReadExecutor
from ontobq.cli import main
from ontobq.orchestrate.plan import DeploymentPlan, PlanBlockedError, build_plan
from ontobq.orchestrate.render import concatenated_sql, dumps_json, plan_payload, unqualified_target
from ontobq.tests.orchestrate_support import (
    FailingExecutor,
    catalog_without_country,
    clean_executor,
    commerce_inspector,
)
from ontobq.tests.paths import FIXTURES_DIR, TESTS_DIR

if TYPE_CHECKING:
    from pathlib import Path

_COMMERCE = FIXTURES_DIR / "commerce.yaml"
_GOLDEN = TESTS_DIR / "goldens" / "plan" / "commerce.json"


def _plan_commerce() -> DeploymentPlan:
    return build_plan(_COMMERCE, inspector=commerce_inspector(), query_executor=clean_executor())


def test_build_plan_blocked_by_integrity_error() -> None:
    domain = load_domain(_COMMERCE)
    query = next(item for item in compile_integrity_queries(domain) if item.code == "OBQ201")
    executor = FakeBigQueryReadExecutor(
        {query.sql: ({"id": None, "violation_count": 1, "total_violations": 1},)}
    )
    with pytest.raises(PlanBlockedError) as caught:
        build_plan(_COMMERCE, inspector=commerce_inspector(), query_executor=executor)
    assert caught.value.validation.has_errors
    assert "OBQ201" in tuple(item.code for item in caught.value.validation.diagnostics)


def test_build_plan_blocked_by_metadata_error() -> None:
    with pytest.raises(PlanBlockedError):
        build_plan(
            _COMMERCE,
            inspector=FakeBigQueryInspector(catalog_without_country()),
            query_executor=FailingExecutor(),
        )


def test_commerce_plan_order_and_compiler_sql() -> None:
    domain = load_domain(_COMMERCE)
    views = compile_mapping_views(domain)
    graph = compile_property_graph(domain, views)
    plan = _plan_commerce()
    kinds = tuple(item.kind for item in plan.artifacts)
    names = tuple(item.semantic_name for item in plan.artifacts)
    assert kinds == ("mapping_view", "mapping_view", "mapping_view", "property_graph")
    assert names == ("Customer", "Order", "PLACED", "commerce")
    assert tuple(item.sql for item in plan.artifacts[:-1]) == tuple(item.sql for item in views)
    assert plan.artifacts[-1].sql == graph.sql


def test_plan_dag_graph_depends_on_every_view() -> None:
    plan = _plan_commerce()
    views = plan.artifacts[:-1]
    graph = plan.artifacts[-1]
    targets = tuple(item.target_name for item in views)
    assert graph.kind == "property_graph"
    assert graph.dependencies == targets
    assert all(item.dependencies == () for item in views)
    assert all(item.kind == "mapping_view" for item in views)


def test_content_hash_is_sha256_of_utf8_sql() -> None:
    plan = _plan_commerce()
    for artifact in plan.artifacts:
        digest = hashlib.sha256(artifact.sql.encode("utf-8")).hexdigest()
        assert artifact.content_hash == digest


def test_commerce_plan_matches_golden_structure() -> None:
    plan = _plan_commerce()
    expected = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    identity = {
        "name": plan.domain_identity.name,
        "project": plan.domain_identity.project,
        "dataset": plan.domain_identity.dataset,
        "graph": plan.domain_identity.graph,
    }
    artifacts = [
        {
            "kind": item.kind,
            "semantic_name": item.semantic_name,
            "target_name": item.target_name,
            "dependencies": list(item.dependencies),
        }
        for item in plan.artifacts
    ]
    assert identity == expected["domain_identity"]
    assert artifacts == expected["artifacts"]


def test_build_plan_is_deterministic() -> None:
    first = _plan_commerce()
    second = _plan_commerce()
    assert first == second
    result = validate_domain(
        _COMMERCE, inspector=commerce_inspector(), query_executor=clean_executor()
    )
    payload = dumps_json(plan_payload(first, result, include_sql=True))
    again = dumps_json(plan_payload(second, result, include_sql=True))
    assert payload == again


def test_reused_validation_matches_fresh_plan() -> None:
    result = validate_domain(
        _COMMERCE, inspector=commerce_inspector(), query_executor=clean_executor()
    )
    reused = build_plan(
        _COMMERCE,
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
        validation=result,
    )
    assert reused == _plan_commerce()


def test_reuse_rejected_when_identity_matches_but_contents_differ() -> None:
    commerce = load_domain(_COMMERCE)
    changed = load_domain(FIXTURES_DIR / "expression-mapping.yaml")
    assert commerce.metadata.name == changed.metadata.name
    assert commerce.bigquery == changed.bigquery
    assert commerce != changed
    result = validate_domain(
        commerce, inspector=commerce_inspector(), query_executor=clean_executor()
    )
    plan = build_plan(
        changed,
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
        validation=result,
    )
    names = tuple(item.semantic_name for item in plan.artifacts)
    assert "Customer" not in names
    assert "PLACED" not in names
    assert "Order" in names


def test_stale_validation_not_reused_after_source_file_change(tmp_path: Path) -> None:
    path = tmp_path / "domain.yaml"
    path.write_text(_COMMERCE.read_text(encoding="utf-8"), encoding="utf-8")
    result = validate_domain(
        path, inspector=commerce_inspector(), query_executor=clean_executor()
    )
    expression = FIXTURES_DIR / "expression-mapping.yaml"
    path.write_text(expression.read_text(encoding="utf-8"), encoding="utf-8")
    plan = build_plan(
        path,
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
        validation=result,
    )
    names = tuple(item.semantic_name for item in plan.artifacts)
    assert "Customer" not in names
    assert "Order" in names


def test_offline_plan_records_integrity_not_ran() -> None:
    plan = build_plan(_COMMERCE, offline_only=True)
    summary = plan.validation_summary
    assert summary.offline_only is True
    assert summary.integrity_ran is False
    assert summary.error_count == 0
    assert plan.artifacts[-1].kind == "property_graph"
    assert all(item.kind == "mapping_view" for item in plan.artifacts[:-1])


def test_expression_and_composite_fixtures_compile_through_plan() -> None:
    expression = build_plan(
        FIXTURES_DIR / "expression-mapping.yaml",
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
    )
    composite = build_plan(
        FIXTURES_DIR / "composite-key.yaml",
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
    )
    assert "Order" in tuple(item.semantic_name for item in expression.artifacts)
    assert "Customer" in tuple(item.semantic_name for item in composite.artifacts)
    assert expression.artifacts[-1].kind == "property_graph"
    assert composite.artifacts[-1].kind == "property_graph"


def test_emit_sql_stdout_matches_artifact_order(capsys: pytest.CaptureFixture[str]) -> None:
    plan = _plan_commerce()
    code = main(
        ["plan", "--format", "human", "--emit-sql", "-", str(_COMMERCE)],
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
    )
    output = capsys.readouterr().out
    assert code == 0
    assert concatenated_sql(plan) in output


def test_emit_sql_directory_uses_unqualified_names(tmp_path: Path) -> None:
    plan = _plan_commerce()
    code = main(
        ["plan", "--emit-sql", str(tmp_path), str(_COMMERCE)],
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
    )
    assert code == 0
    for artifact in plan.artifacts:
        written = (tmp_path / f"{unqualified_target(artifact.target_name)}.sql").read_text(
            encoding="utf-8"
        )
        expected = artifact.sql if artifact.sql.endswith("\n") else f"{artifact.sql}\n"
        assert written == expected


def test_plan_cli_json_omits_sql_without_emit(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["plan", "--format", "json", str(_COMMERCE)],
        inspector=commerce_inspector(),
        query_executor=clean_executor(),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert "sql" not in payload["artifacts"][0]
    assert payload["artifacts"][0]["content_hash"]


def test_apply_subcommand_is_absent() -> None:
    with pytest.raises(SystemExit):
        main(["apply", str(_COMMERCE)])
