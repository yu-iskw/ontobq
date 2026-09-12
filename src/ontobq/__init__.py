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

"""OntoBQ: ontology-as-code Domain IR for BigQuery Property Graph."""

from ontobq.bigquery import (
    BigQueryInspector,
    ColumnSnapshot,
    FakeBigQueryInspector,
    ScalarDryRunResult,
    SourceSnapshot,
)
from ontobq.bq import (
    BigQueryReadExecutor,
    FakeBigQueryReadExecutor,
    QueryEstimate,
)
from ontobq.compile import (
    MappingViewArtifact,
    PropertyGraphArtifact,
    compile_mapping_views,
    compile_property_graph,
)
from ontobq.diagnostics import Diagnostic, DomainLoadError, Severity
from ontobq.ir import (
    BigQueryEntityMapping,
    BigQueryRelationshipMapping,
    BigQueryTarget,
    ColumnMapping,
    Domain,
    EntityDefinition,
    ExpressionMapping,
    Metadata,
    PropertyDefinition,
    PropertyType,
    RelationshipDefinition,
)
from ontobq.load import load_domain
from ontobq.naming import (
    edge_key_column,
    edge_view_name,
    from_key_column,
    node_view_name,
    normalize_view_segment,
    to_key_column,
)
from ontobq.schema import API_VERSION, KIND, SCHEMA_ID, load_v1alpha1_schema
from ontobq.validate import (
    IntegrityExecutionError,
    IntegrityQuery,
    IntegrityReport,
    compile_integrity_queries,
    validate_bigquery_metadata,
    validate_integrity,
)

__all__ = [
    "API_VERSION",
    "KIND",
    "SCHEMA_ID",
    "BigQueryEntityMapping",
    "BigQueryInspector",
    "BigQueryReadExecutor",
    "BigQueryRelationshipMapping",
    "BigQueryTarget",
    "ColumnMapping",
    "ColumnSnapshot",
    "Diagnostic",
    "Domain",
    "DomainLoadError",
    "EntityDefinition",
    "ExpressionMapping",
    "FakeBigQueryInspector",
    "FakeBigQueryReadExecutor",
    "IntegrityExecutionError",
    "IntegrityQuery",
    "IntegrityReport",
    "MappingViewArtifact",
    "Metadata",
    "PropertyDefinition",
    "PropertyGraphArtifact",
    "PropertyType",
    "QueryEstimate",
    "RelationshipDefinition",
    "ScalarDryRunResult",
    "Severity",
    "SourceSnapshot",
    "compile_integrity_queries",
    "compile_mapping_views",
    "compile_property_graph",
    "edge_key_column",
    "edge_view_name",
    "from_key_column",
    "load_domain",
    "load_v1alpha1_schema",
    "node_view_name",
    "normalize_view_segment",
    "to_key_column",
    "validate_bigquery_metadata",
    "validate_integrity",
]
