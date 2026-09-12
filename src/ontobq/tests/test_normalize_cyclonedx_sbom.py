# Copyright 2025 yu-iskw
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for CycloneDX SBOM normalization used by make sbom-check."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest  # pyright: ignore[reportMissingImports]

REPO_ROOT = Path(__file__).resolve().parents[3]
NORMALIZE_SCRIPT = REPO_ROOT / "dev" / "normalize_cyclonedx_sbom.py"


def _load_normalize_module() -> dict[str, Any]:
    """Load the normalize script as a module without installing it."""
    return runpy.run_path(str(NORMALIZE_SCRIPT))


def test_normalize_cyclonedx_sbom_rewrites_spec_version(tmp_path: Path) -> None:
    """Trivy 1.7 documents are rewritten to CycloneDX 1.6 for Grype."""
    normalize_module = _load_normalize_module()
    sbom_path = tmp_path / "sbom.cdx.json"
    sbom_path.write_text(
        json.dumps(
            {
                "$schema": "http://cyclonedx.org/schema/bom-1.7.schema.json",
                "bomFormat": "CycloneDX",
                "specVersion": "1.7",
                "version": 1,
                "components": [],
            }
        ),
        encoding="utf-8",
    )

    normalize_module["normalize_cyclonedx_sbom"](sbom_path)

    rewritten = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert rewritten["specVersion"] == "1.6"
    assert rewritten["$schema"] == "http://cyclonedx.org/schema/bom-1.6.schema.json"
    assert rewritten["bomFormat"] == "CycloneDX"


def test_normalize_cyclonedx_sbom_rejects_non_cyclonedx(tmp_path: Path) -> None:
    """Non-CycloneDX JSON must fail loudly."""
    normalize_module = _load_normalize_module()
    sbom_path = tmp_path / "not-sbom.json"
    sbom_path.write_text(json.dumps({"bomFormat": "SPDX"}), encoding="utf-8")

    with pytest.raises(SystemExit, match="bomFormat must be CycloneDX"):
        normalize_module["normalize_cyclonedx_sbom"](sbom_path)


def test_normalize_cyclonedx_sbom_rejects_non_object(tmp_path: Path) -> None:
    """Top-level JSON arrays must fail loudly."""
    normalize_module = _load_normalize_module()
    sbom_path = tmp_path / "array.json"
    sbom_path.write_text("[]", encoding="utf-8")

    with pytest.raises(SystemExit, match="expected a JSON object"):
        normalize_module["normalize_cyclonedx_sbom"](sbom_path)


def test_normalize_cyclonedx_sbom_skips_rewrite_when_already_16(
    tmp_path: Path,
) -> None:
    """Already-normalized documents are left unchanged on disk."""
    normalize_module = _load_normalize_module()
    sbom_path = tmp_path / "sbom.cdx.json"
    payload = {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [],
    }
    sbom_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    before = sbom_path.read_bytes()

    normalize_module["normalize_cyclonedx_sbom"](sbom_path)

    assert sbom_path.read_bytes() == before
