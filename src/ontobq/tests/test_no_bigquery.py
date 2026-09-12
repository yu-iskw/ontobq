"""Package boundary: google.cloud stays in the BigQuery adapter module."""

from __future__ import annotations

import sys
from pathlib import Path

import ontobq
from ontobq import load_domain
from ontobq.bigquery.fake import FakeBigQueryInspector
from ontobq.tests.paths import FIXTURES_DIR
from ontobq.validate.bq_metadata import validate_bigquery_metadata

_GOOGLE_ADAPTER = Path("bigquery") / "google.py"


def _is_google_adapter(path: Path, root: Path) -> bool:
    return path.resolve() == (root / _GOOGLE_ADAPTER).resolve()


def test_no_bigquery_client_import() -> None:
    load_domain(FIXTURES_DIR / "commerce.yaml")
    assert not any("google.cloud.bigquery" in name for name in sys.modules)
    assert "google.cloud" not in sys.modules


def test_validator_and_fake_do_not_import_google() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    validate_bigquery_metadata(domain, FakeBigQueryInspector())
    assert not any("google.cloud.bigquery" in name for name in sys.modules)
    assert "google.cloud" not in sys.modules


def test_production_modules_do_not_import_google() -> None:
    root = Path(ontobq.__file__).resolve().parent
    for path in root.rglob("*.py"):
        if "tests" in path.parts or _is_google_adapter(path, root):
            continue
        text = path.read_text(encoding="utf-8")
        assert "google.cloud" not in text
        assert "from google" not in text
