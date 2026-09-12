"""Google adapter isolation: SDK imports stay in bigquery/google.py."""

from __future__ import annotations

from pathlib import Path

import ontobq

_ADAPTER = Path(ontobq.__file__).resolve().parent / "bigquery" / "google.py"


def test_google_adapter_contains_dry_run_config() -> None:
    text = _ADAPTER.read_text(encoding="utf-8")
    assert "google.cloud" in text
    assert "QueryJobConfig" in text
    assert "GoogleBigQueryInspector" in text
    assert "CREATE OR REPLACE VIEW" not in text
    assert "PROPERTY GRAPH" not in text


def test_only_google_adapter_imports_google_cloud() -> None:
    root = Path(ontobq.__file__).resolve().parent
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or path == _ADAPTER:
            continue
        text = path.read_text(encoding="utf-8")
        if "google.cloud" in text or "from google" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
