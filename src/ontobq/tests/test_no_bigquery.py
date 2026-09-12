"""Package boundary: no BigQuery client in the issue 9 slice."""

from __future__ import annotations

import sys
from pathlib import Path

import ontobq
from ontobq import load_domain
from ontobq.tests.paths import FIXTURES_DIR


def test_no_bigquery_client_import() -> None:
    load_domain(FIXTURES_DIR / "commerce.yaml")
    assert not any("google.cloud.bigquery" in name for name in sys.modules)
    assert "google.cloud" not in sys.modules


def test_production_modules_do_not_import_google() -> None:
    root = Path(ontobq.__file__).resolve().parent
    for path in root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert "google.cloud" not in text
        assert "from google" not in text
