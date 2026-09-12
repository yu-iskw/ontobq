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

"""Shared machine-readable diagnostics for loaders and later validators."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    """Diagnostic severity distinguishable without parsing ``message``."""

    ERROR = "error"
    WARNING = "warning"


STRUCTURAL_ERROR_CODE = "OBQ000"


@dataclass(frozen=True)
class Diagnostic:
    """Stable diagnostic consumed by semantics, metadata, integrity, and CLI."""

    code: str
    severity: Severity
    path: str
    message: str
    evidence: tuple[str, ...] = ()


class DomainLoadError(Exception):
    """Raised when a Domain document fails to parse or structurally validate."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        super().__init__(_format_load_error(diagnostics))


def _format_load_error(diagnostics: tuple[Diagnostic, ...]) -> str:
    if not diagnostics:
        return "domain document is invalid"
    first = diagnostics[0]
    prefix = f"{first.code} at {first.path}: {first.message}"
    if len(diagnostics) == 1:
        return prefix
    return f"{len(diagnostics)} structural errors; first {prefix}"
