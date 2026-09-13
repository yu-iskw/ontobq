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

"""Thin ``ontobq`` CLI: formatter and exit-code adapter over validate/plan APIs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ontobq.bigquery.google import GoogleBigQueryInspector, GoogleBigQueryReadExecutor
from ontobq.orchestrate.plan import PlanBlockedError, build_plan
from ontobq.orchestrate.render import (
    concatenated_sql,
    dumps_json,
    format_plan_human,
    format_validation_human,
    plan_payload,
    validation_payload,
    write_sql_directory,
)
from ontobq.orchestrate.validate import ValidationResult, validate_domain

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ontobq.bigquery.inspector import BigQueryInspector
    from ontobq.bq.executor import BigQueryReadExecutor
    from ontobq.orchestrate.plan import DeploymentPlan

_POLICY_HELP = """\
Default validate/plan runs layers 1-4 (load, semantics, metadata, integrity) and
requires a BigQuery inspector and query executor. --offline runs load and
semantics only and does not construct BigQuery clients. --skip-integrity runs
layers 1-3 (inspector required; no data scans). --offline implies integrity off.
Plans produced offline or without integrity are not apply-safe.
"""


def main(
    argv: Sequence[str] | None = None,
    *,
    inspector: BigQueryInspector | None = None,
    query_executor: BigQueryReadExecutor | None = None,
) -> int:
    """CLI entry. Returns 0 iff there are no error-level diagnostics and plan succeeded."""

    args = _parse_args(argv)
    clients = _resolve_clients(args, inspector, query_executor)
    if args.command == "validate":
        return _run_validate(args, clients[0], clients[1])
    return _run_plan(args, clients[0], clients[1])


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ontobq",
        description="Read-only Domain validation and deployment planning.",
        epilog=_POLICY_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_validate_parser(subparsers)
    _add_plan_parser(subparsers)
    parsed = list(argv) if argv is not None else None
    return parser.parse_args(parsed)


def _shared_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run load and semantics only. Do not construct BigQuery clients.",
    )
    parser.add_argument(
        "--skip-integrity",
        action="store_true",
        help="Skip data-integrity scans. Still requires an inspector unless --offline.",
    )
    parser.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Diagnostic/plan presentation. JSON codes are machine-readable.",
    )
    parser.add_argument("domain", type=Path, help="Path to a Domain YAML or JSON document.")


def _add_validate_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "validate",
        help="Validate a Domain document. Never mutates BigQuery.",
        description="Run cost-aware validation layers. Never mutates BigQuery.",
        epilog=_POLICY_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _shared_flags(parser)


def _add_plan_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "plan",
        help="Build a read-only deployment plan. Never mutates BigQuery.",
        description="Validate, then compile mapping views and the property graph.",
        epilog=_POLICY_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _shared_flags(parser)
    parser.add_argument(
        "--emit-sql",
        metavar="TARGET",
        default=None,
        help="Write SQL: '-' concatenates to stdout; DIR writes one file per artifact.",
    )


def _offline_only(args: argparse.Namespace) -> bool:
    return bool(args.offline)


def _include_integrity(args: argparse.Namespace) -> bool:
    return not args.offline and not args.skip_integrity


def _resolve_clients(
    args: argparse.Namespace,
    inspector: BigQueryInspector | None,
    query_executor: BigQueryReadExecutor | None,
) -> tuple[BigQueryInspector | None, BigQueryReadExecutor | None]:
    if _offline_only(args):
        return None, None
    resolved_inspector = inspector if inspector is not None else GoogleBigQueryInspector()
    if not _include_integrity(args):
        return resolved_inspector, None
    resolved_executor = (
        query_executor if query_executor is not None else GoogleBigQueryReadExecutor()
    )
    return resolved_inspector, resolved_executor


def _print(text: str) -> None:
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")


def _run_validate(
    args: argparse.Namespace,
    inspector: BigQueryInspector | None,
    query_executor: BigQueryReadExecutor | None,
) -> int:
    result = validate_domain(
        args.domain,
        inspector=inspector,
        query_executor=query_executor,
        offline_only=_offline_only(args),
        include_integrity=_include_integrity(args),
    )
    _print(_render_validation(result, args.format))
    if result.has_errors:
        return 1
    return 0


def _render_validation(result: ValidationResult, fmt: str) -> str:
    if fmt == "json":
        return dumps_json(validation_payload(result))
    return format_validation_human(result)


def _run_plan(
    args: argparse.Namespace,
    inspector: BigQueryInspector | None,
    query_executor: BigQueryReadExecutor | None,
) -> int:
    result = validate_domain(
        args.domain,
        inspector=inspector,
        query_executor=query_executor,
        offline_only=_offline_only(args),
        include_integrity=_include_integrity(args),
    )
    try:
        plan = build_plan(
            args.domain,
            inspector=inspector,
            query_executor=query_executor,
            offline_only=_offline_only(args),
            include_integrity=_include_integrity(args),
            validation=result,
        )
    except PlanBlockedError as error:
        _print(_render_validation(error.validation, args.format))
        return 1
    _print(_render_plan(plan, result, args.format, args.emit_sql))
    return 0


def _render_plan(
    plan: DeploymentPlan,
    result: ValidationResult,
    fmt: str,
    emit_sql: str | None,
) -> str:
    include_sql = emit_sql is not None
    if emit_sql is not None and emit_sql != "-":
        write_sql_directory(plan, Path(emit_sql))
    if fmt == "json":
        return dumps_json(plan_payload(plan, result, include_sql=include_sql))
    return _human_plan_output(plan, emit_sql)


def _human_plan_output(plan: DeploymentPlan, emit_sql: str | None) -> str:
    summary = format_plan_human(plan)
    if emit_sql != "-":
        return summary + "\n"
    return f"{summary}\n\n{concatenated_sql(plan)}"


if __name__ == "__main__":
    sys.exit(main())
