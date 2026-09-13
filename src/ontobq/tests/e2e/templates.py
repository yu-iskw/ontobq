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

"""Load E2E templates and interpolate the allowlisted project/dataset/graph."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ontobq.tests.e2e.gates import GRAPH_NAME, RFC_FIXTURE_PROJECT

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PROJECT_TOKEN = "${ONTOBQ_E2E_PROJECT}"  # noqa: S105 -- interpolation placeholder, not a secret
DATASET_TOKEN = "${ONTOBQ_E2E_DATASET}"  # noqa: S105 -- interpolation placeholder, not a secret
GRAPH_TOKEN = "${ONTOBQ_E2E_GRAPH}"  # noqa: S105 -- interpolation placeholder, not a secret
RUN_ID_TOKEN = "${ONTOBQ_E2E_RUN_ID}"  # noqa: S105 -- interpolation placeholder, not a secret
HAPPY_YAML = "commerce_e2e.yaml"
SEED_SQL = "seed.sql"
TEARDOWN_SQL = "teardown.sql"
SEED_FILES = (
    "seed.sql",
    "schema_obq104.sql",
    "dirty_obq202.sql",
    "dirty_obq204.sql",
    "dirty_obq205.sql",
    "dirty_obq206.sql",
)
NEGATIVE_FILES = (
    ("OBQ102", "invalid_obq102.yaml"),
    ("OBQ104", "invalid_obq104.yaml"),
    ("OBQ202", "invalid_obq202.yaml"),
    ("OBQ204", "invalid_obq204.yaml"),
    ("OBQ205", "invalid_obq205.yaml"),
    ("OBQ206", "invalid_obq206.yaml"),
)


@dataclass(frozen=True)
class RunCoordinates:
    """Project/dataset/graph/run-id bundle threaded through template interpolation.

    ``run_id`` (see ``gates.new_run_id``) is appended to every generated
    domain, graph, view, and table name so parallel sessions sharing one
    allowlisted project/dataset never collide.
    """

    project: str
    dataset: str
    graph: str = GRAPH_NAME
    run_id: str = ""


def fixture_path(name: str) -> Path:
    """Return a path under ``tests/e2e/fixtures``."""

    return FIXTURES_DIR / name


_ALL_TOKENS = (PROJECT_TOKEN, DATASET_TOKEN, GRAPH_TOKEN, RUN_ID_TOKEN)


def _reject_token_injection(coords: RunCoordinates) -> None:
    """Refuse coordinate values that themselves contain an interpolation token.

    ``substitute_tokens`` applies ``str.replace`` once per token, in sequence.
    Without this guard, a value that happens to contain another token's exact
    text -- e.g. a misconfigured ``ONTOBQ_E2E_DATASET`` containing the literal
    substring ``${ONTOBQ_E2E_RUN_ID}`` -- would be silently rewritten by a
    later replacement instead of being rejected, letting ``_seed`` run DDL
    against a dataset the caller never actually specified.
    """

    for value in (coords.project, coords.dataset, coords.graph, coords.run_id):
        if any(token in value for token in _ALL_TOKENS):
            raise ValueError("E2E coordinate value contains an unresolved interpolation token")


def substitute_tokens(text: str, coords: RunCoordinates) -> str:
    """Replace project/dataset/graph/run-id tokens. Refuse leftover RFC or unresolved tokens."""

    _reject_token_injection(coords)
    rendered = (
        text.replace(PROJECT_TOKEN, coords.project)
        .replace(DATASET_TOKEN, coords.dataset)
        .replace(GRAPH_TOKEN, coords.graph)
        .replace(RUN_ID_TOKEN, coords.run_id)
    )
    if RFC_FIXTURE_PROJECT in rendered:
        raise ValueError("refusing to materialize RFC fixture project my-project")
    if any(token in rendered for token in _ALL_TOKENS):
        raise ValueError("unresolved E2E interpolation tokens remain")
    return rendered


def materialize_text(name: str, coords: RunCoordinates) -> str:
    """Read a fixture file and interpolate live coordinates."""

    original = fixture_path(name).read_text(encoding="utf-8")
    return substitute_tokens(original, coords)


def materialize_file(name: str, destination: Path, coords: RunCoordinates) -> Path:
    """Write an interpolated fixture copy and return the destination path."""

    destination.write_text(materialize_text(name, coords), encoding="utf-8")
    return destination


def sql_statements(script: str) -> tuple[str, ...]:
    """Split a semicolon-delimited SQL script, dropping comment-only chunks."""

    return tuple(part for part in (chunk.strip() for chunk in script.split(";")) if _has_sql(part))


def _has_sql(statement: str) -> bool:
    return any(
        line.strip() and not line.strip().startswith("--") for line in statement.splitlines()
    )
