"""Fixture and example paths for ontobq tests."""

from pathlib import Path

_TEST_FILE = Path(__file__).resolve()
TESTS_DIR = _TEST_FILE.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
REPO_ROOT = _TEST_FILE.parents[3]
EXAMPLES_DIR = REPO_ROOT / "examples"
SCHEMA_PATH = _TEST_FILE.parents[1] / "schema" / "v1alpha1.json"
