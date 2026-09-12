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

"""Explicit v1alpha1 semantic-to-physical type compatibility. No silent coercions."""

from __future__ import annotations

from ontobq.ir import PropertyType

COMPATIBLE_PHYSICAL_TYPES: dict[PropertyType, frozenset[str]] = {
    PropertyType.STRING: frozenset({"STRING"}),
    PropertyType.INTEGER: frozenset({"INT64"}),
    PropertyType.NUMBER: frozenset({"FLOAT64", "NUMERIC", "BIGNUMERIC"}),
    PropertyType.BOOLEAN: frozenset({"BOOL"}),
    PropertyType.DATE: frozenset({"DATE"}),
    PropertyType.DATETIME: frozenset({"DATETIME"}),
    PropertyType.TIME: frozenset({"TIME"}),
    PropertyType.TIMESTAMP: frozenset({"TIMESTAMP"}),
    PropertyType.BYTES: frozenset({"BYTES"}),
    PropertyType.JSON: frozenset({"JSON"}),
    PropertyType.GEOGRAPHY: frozenset({"GEOGRAPHY"}),
}


def _is_non_scalar(physical: str, mode: str) -> bool:
    if mode.strip().upper() == "REPEATED":
        return True
    compact = physical.strip().upper().replace(" ", "")
    return compact.startswith(("ARRAY", "STRUCT", "RECORD"))


def physical_type_compatible(semantic: PropertyType, physical: str, mode: str) -> bool:
    """Return True when ``physical`` may back ``semantic`` without CAST."""

    if _is_non_scalar(physical, mode):
        return False
    allowed = COMPATIBLE_PHYSICAL_TYPES.get(semantic, frozenset())
    return physical in allowed
