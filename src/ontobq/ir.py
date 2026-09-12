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

"""Typed Domain IR mirroring the ontobq.dev/v1alpha1 public contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class PropertyType(str, Enum):
    """Semantic property types encoded by the v1alpha1 JSON Schema enum."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    TIMESTAMP = "timestamp"
    BYTES = "bytes"
    JSON = "json"
    GEOGRAPHY = "geography"


@dataclass(frozen=True)
class ColumnMapping:
    """Physical mapping that reads one source column."""

    column: str


@dataclass(frozen=True)
class ExpressionMapping:
    """Physical mapping that uses a trusted scalar GoogleSQL expression."""

    expression: str


MappingValue = ColumnMapping | ExpressionMapping


@dataclass(frozen=True)
class Metadata:
    """Domain identity and optional human-facing labels."""

    name: str
    display_name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class BigQueryTarget:
    """Deployment target for compiled views and the property graph."""

    project: str
    dataset: str
    graph: str


@dataclass(frozen=True)
class PropertyDefinition:
    """Declared semantic property."""

    type: PropertyType
    nullable: bool = True


@dataclass(frozen=True)
class BigQueryEntityMapping:
    """Physical source and property mappings for one entity."""

    source: str
    properties: Mapping[str, MappingValue]


@dataclass(frozen=True)
class EntityDefinition:
    """Semantic entity with keys, properties, and a BigQuery mapping."""

    key: tuple[str, ...]
    properties: Mapping[str, PropertyDefinition]
    mapping: BigQueryEntityMapping
    description: str | None = None


@dataclass(frozen=True)
class BigQueryRelationshipMapping:
    """Physical source, element keys, and endpoint mappings for one relationship."""

    source: str
    key: tuple[MappingValue, ...]
    from_endpoint: Mapping[str, MappingValue]
    to_endpoint: Mapping[str, MappingValue]
    properties: Mapping[str, MappingValue]


@dataclass(frozen=True)
class RelationshipDefinition:
    """Semantic relationship between two entities."""

    from_entity: str
    to_entity: str
    mapping: BigQueryRelationshipMapping
    properties: Mapping[str, PropertyDefinition]
    description: str | None = None


@dataclass(frozen=True)
class Domain:
    """In-process Domain document. Downstream code must consume this, not YAML."""

    api_version: str
    kind: str
    metadata: Metadata
    bigquery: BigQueryTarget
    entities: Mapping[str, EntityDefinition]
    relationships: Mapping[str, RelationshipDefinition]
