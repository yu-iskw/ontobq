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

"""Offline proof that ``pytest -m e2e`` collects every test under ``tests/e2e``.

A bare module-level ``pytestmark`` assigned in ``tests/e2e/conftest.py`` only
marks tests defined in that same module (there are none: it holds only
fixtures). It does not propagate to sibling test modules such as
``test_mvp_happy_path.py``, so ``pytest -m e2e`` would otherwise silently
select nothing and ``make test-e2e`` would report a false "no tests ran"
success. ``conftest.py`` instead defines a directory-scoped
``pytest_itemcollected`` hook that tags every item collected under
``tests/e2e`` with ``pytest.mark.e2e``; this test proves that hook actually
selects the full suite, using only ``--collect-only`` (no live BigQuery call).
"""

from __future__ import annotations

import subprocess
import sys

from ontobq.tests.paths import REPO_ROOT

_E2E_DIR = REPO_ROOT / "src" / "ontobq" / "tests" / "e2e"

# pytest's own exit code for "collection succeeded, zero tests matched" -- its
# normal outcome when a marker expression deselects everything, not a failure.
_NO_TESTS_COLLECTED_EXIT_CODE = 5
_OK_COLLECT_EXIT_CODES = (0, _NO_TESTS_COLLECTED_EXIT_CODE)


def _collected_node_ids(*extra_args: str) -> set[str]:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(_E2E_DIR), *extra_args],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode not in _OK_COLLECT_EXIT_CODES:
        raise AssertionError(f"pytest --collect-only failed:\n{result.stdout}\n{result.stderr}")
    return {line for line in result.stdout.splitlines() if "::" in line}


def test_e2e_marker_hook_selects_every_test_under_the_directory() -> None:
    """``pytest -m e2e`` must select exactly the tests ``--collect-only`` finds."""

    all_tests = _collected_node_ids()
    marked_tests = _collected_node_ids("-m", "e2e")
    assert all_tests
    assert marked_tests == all_tests


def test_e2e_marker_hook_deselects_when_marker_expression_excludes_it() -> None:
    """``-m "not e2e"`` (what default ``make test`` uses) must select none of them."""

    all_tests = _collected_node_ids()
    unmarked_tests = _collected_node_ids("-m", "not e2e")
    assert all_tests
    assert not unmarked_tests
