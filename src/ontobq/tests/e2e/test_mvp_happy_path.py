"""Happy-path live BigQuery MVP: YAML through apply, second apply, GQL."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

from ontobq import apply_plan, build_plan, load_domain, node_view_name, validate_domain
from ontobq.cli import main
from ontobq.naming import edge_view_name
from ontobq.orchestrate.validate import (
    LAYER_INTEGRITY,
    LAYER_LOAD,
    LAYER_METADATA,
    LAYER_SEMANTICS,
)
from ontobq.tests.e2e.gql import (
    COMPOSITE_ROWS,
    MULTI_HOP_ROWS,
    SINGLE_HOP_ROWS,
    composite_item_sql,
    multi_hop_sql,
    single_hop_sql,
)
from ontobq.tests.e2e.lifecycle import graph_target
from ontobq.tests.e2e.recording import RecordingMutationExecutor

if TYPE_CHECKING:
    import pytest  # pyright: ignore[reportMissingImports]

    from ontobq.orchestrate.plan import DeploymentPlan
    from ontobq.tests.e2e.conftest import LiveE2E

_LAYERS = (LAYER_LOAD, LAYER_SEMANTICS, LAYER_METADATA, LAYER_INTEGRITY)


def _plan(live: LiveE2E) -> DeploymentPlan:
    return build_plan(
        live.domain_path,
        inspector=live.inspector,
        query_executor=live.query_executor,
    )


def _row_values(row: object) -> dict[str, str]:
    mapping = dict(row)  # pyright: ignore[reportCallIssue, reportArgumentType]
    return {str(key): str(mapping[key]) for key in mapping}


def test_domain_loads_structurally(e2e_live: LiveE2E) -> None:
    domain = load_domain(e2e_live.domain_path)
    assert domain.metadata.name == e2e_live.domain_name
    assert domain.bigquery.project == e2e_live.project
    assert domain.bigquery.dataset == e2e_live.dataset
    assert tuple(domain.entities) == ("Customer", "Order", "OrderItem", "Product")
    assert tuple(domain.relationships) == ("PLACED", "CONTAINS", "OF")


def _bound_client_project(adapter: object) -> str:
    """Return the live BigQuery project's id on ``adapter``'s SDK client.

    ``SdkShapedClient`` only names the methods inspectors/executors call, so
    ``.project`` is not on the protocol. ``getattr`` keeps this assertion on
    the real ``google.cloud.bigquery.Client`` without protected-member lint.
    """

    project = getattr(getattr(adapter, "_client", None), "project", None)
    if not isinstance(project, str) or not project:
        raise AssertionError(f"{type(adapter).__name__} is not bound to a project")
    return project


def test_read_clients_resolve_to_the_gated_project(e2e_live: LiveE2E) -> None:
    """Inspector and read-executor must never fall back to ADC's default project.

    Both are constructed in ``conftest._build_live`` from one
    ``bigquery.Client(project=...)`` shared with the mutator; assert the
    underlying client's own ``project`` (not just query text) is the gated
    ``ONTOBQ_E2E_PROJECT``, so metadata dry runs and integrity/GQL queries
    cannot silently run against (and bill) a different project.
    """

    assert _bound_client_project(e2e_live.inspector) == e2e_live.project
    assert _bound_client_project(e2e_live.query_executor) == e2e_live.project
    assert e2e_live.mutator.identity.project == e2e_live.project


def test_four_validation_layers_pass(e2e_live: LiveE2E) -> None:
    result = validate_domain(
        e2e_live.domain_path,
        inspector=e2e_live.inspector,
        query_executor=e2e_live.query_executor,
    )
    assert result.layers_run == _LAYERS
    assert not result.has_errors
    assert result.domain is not None


def test_cli_validate_json_subprocess_is_ok(e2e_live: LiveE2E) -> None:
    # The CLI's default inspector/read-executor construct google.cloud.bigquery.Client()
    # with no project override, so they fall back to ADC's default project unless
    # GOOGLE_CLOUD_PROJECT names the gated project explicitly.
    env = {**os.environ, "GOOGLE_CLOUD_PROJECT": e2e_live.project}
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "ontobq.cli",
            "validate",
            "--format",
            "json",
            str(e2e_live.domain_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["ok"] is True
    assert payload["layers_run"] == list(_LAYERS)
    assert payload["diagnostics"] == []


def test_plan_orders_views_then_graph(e2e_live: LiveE2E) -> None:
    plan = _plan(e2e_live)
    kinds = tuple(item.kind for item in plan.artifacts)
    assert kinds[-1] == "property_graph"
    assert set(kinds[:-1]) == {"mapping_view"}
    customer = node_view_name(e2e_live.domain_name, "Customer")
    placed = edge_view_name(e2e_live.domain_name, "PLACED")
    targets = tuple(item.target_name for item in plan.artifacts)
    assert any(target.endswith(customer) for target in targets)
    assert any(target.endswith(placed) for target in targets)
    graph_name = graph_target(e2e_live.project, e2e_live.dataset, e2e_live.graph)
    assert plan.artifacts[-1].target_name == graph_name


def test_second_apply_is_safe(e2e_live: LiveE2E, capsys: pytest.CaptureFixture[str]) -> None:
    plan = _plan(e2e_live)
    recording = RecordingMutationExecutor(e2e_live.mutator)
    result = apply_plan(plan, recording)
    assert result.ok
    assert not result.refused
    names = tuple(item.target_name for item in plan.artifacts)
    assert tuple(name for name, _ in recording.calls) == names
    code = main(
        ["apply", "--format", "json", str(e2e_live.domain_path)],
        inspector=e2e_live.inspector,
        query_executor=e2e_live.query_executor,
        mutator=e2e_live.mutator,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["refused"] is False


def test_gql_single_and_multi_hop_rows(e2e_live: LiveE2E) -> None:
    graph = graph_target(e2e_live.project, e2e_live.dataset, e2e_live.graph)
    executor = e2e_live.query_executor
    single = executor.query(single_hop_sql(graph), max_rows=20)
    multi = executor.query(multi_hop_sql(graph), max_rows=20)
    assert tuple(_row_values(row) for row in single) == SINGLE_HOP_ROWS
    assert tuple(_row_values(row) for row in multi) == MULTI_HOP_ROWS
    assert ":Customer" in single_hop_sql(graph) or "Customer" in single_hop_sql(graph)
    assert "`OF`" in multi_hop_sql(graph)


def test_composite_orderitem_key_live(e2e_live: LiveE2E) -> None:
    graph_sql = _plan(e2e_live).artifacts[-1].sql
    assert "KEY (orderId, sku)" in graph_sql
    assert "REFERENCES OrderItem (orderId, sku)" in graph_sql
    graph = graph_target(e2e_live.project, e2e_live.dataset, e2e_live.graph)
    rows = e2e_live.query_executor.query(composite_item_sql(graph), max_rows=20)
    assert tuple(_row_values(row) for row in rows) == COMPOSITE_ROWS
