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

"""Packaged Draft 2020-12 schema for ontobq.dev/v1alpha1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_RESOURCE = "v1alpha1.json"
SCHEMA_ID = "https://ontobq.dev/schemas/v1alpha1.json"
API_VERSION = "ontobq.dev/v1alpha1"
KIND = "Domain"


def load_v1alpha1_schema() -> dict[str, Any]:
    """Return the authoritative v1alpha1 JSON Schema document."""
    schema_path = Path(__file__).resolve().parent / SCHEMA_RESOURCE
    payload = schema_path.read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(payload)
    return loaded
