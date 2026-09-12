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

"""Deterministic v1alpha1 names for generated mapping views and helper columns.

v1alpha1 normalization policy: view-name segments are ASCII-lowercased. Schema
identifiers are already ``[A-Za-z][A-Za-z0-9_]*``, so no further slugification
is applied. Helper-column suffixes keep the semantic key name as written.
"""

from __future__ import annotations

_VIEW_PREFIX = "_ontobq"
_HELPER_PREFIX = "__ontobq"


def normalize_view_segment(identifier: str) -> str:
    """Lowercase a semantic identifier for a generated view-name segment."""
    return identifier.lower()


def node_view_name(domain: str, entity: str) -> str:
    """Render ``_ontobq_<domain>_n_<entity>``."""
    domain_part = normalize_view_segment(domain)
    entity_part = normalize_view_segment(entity)
    return f"{_VIEW_PREFIX}_{domain_part}_n_{entity_part}"


def edge_view_name(domain: str, relationship: str) -> str:
    """Render ``_ontobq_<domain>_e_<relationship>``."""
    domain_part = normalize_view_segment(domain)
    relationship_part = normalize_view_segment(relationship)
    return f"{_VIEW_PREFIX}_{domain_part}_e_{relationship_part}"


def edge_key_column(ordinal: int) -> str:
    """Render ``__ontobq_edge_key_<ordinal>``."""
    return f"{_HELPER_PREFIX}_edge_key_{ordinal}"


def from_key_column(semantic_key_name: str) -> str:
    """Render ``__ontobq_from_<semantic-key-name>``."""
    return f"{_HELPER_PREFIX}_from_{semantic_key_name}"


def to_key_column(semantic_key_name: str) -> str:
    """Render ``__ontobq_to_<semantic-key-name>``."""
    return f"{_HELPER_PREFIX}_to_{semantic_key_name}"
