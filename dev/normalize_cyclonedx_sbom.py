#!/usr/bin/env python3
"""Normalize Trivy CycloneDX JSON so Grype can decode it.

Trivy 0.71 emits CycloneDX specVersion 1.7. Grype 0.112 (via Syft) does not
recognize 1.7 and fails with \"sbom format not recognized\". Rewrite the
document to CycloneDX 1.6 in place. This is a label/schema rewrite for
interoperability with the pinned scanners; it does not strip hypothetical
1.7-only fields.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TARGET_SPEC_VERSION = "1.6"
TARGET_SCHEMA = "http://cyclonedx.org/schema/bom-1.6.schema.json"


def normalize_cyclonedx_sbom(path: Path) -> None:
    """Rewrite *path* so bomFormat CycloneDX documents declare specVersion 1.6."""
    document: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit(f"{path}: expected a JSON object, got {type(document).__name__}")
    bom_format = document.get("bomFormat")
    if bom_format != "CycloneDX":
        raise SystemExit(f"{path}: bomFormat must be CycloneDX, got {bom_format!r}")
    if (
        document.get("specVersion") == TARGET_SPEC_VERSION
        and document.get("$schema") == TARGET_SCHEMA
    ):
        return
    document["specVersion"] = TARGET_SPEC_VERSION
    document["$schema"] = TARGET_SCHEMA
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sbom_path",
        type=Path,
        help="Path to a CycloneDX JSON SBOM file to normalize in place",
    )
    args = parser.parse_args()
    if not args.sbom_path.is_file():
        print(f"error: SBOM file not found: {args.sbom_path}", file=sys.stderr)
        return 1
    normalize_cyclonedx_sbom(args.sbom_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
