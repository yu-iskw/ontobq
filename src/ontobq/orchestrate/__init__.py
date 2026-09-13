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

"""Validate/plan/apply orchestration. Owns sequencing, not OBQ rules or SQL."""

from ontobq.orchestrate.apply import ApplyResult, ArtifactApplyStatus, apply_plan
from ontobq.orchestrate.plan import (
    DeploymentPlan,
    DomainIdentity,
    PlanArtifact,
    PlanBlockedError,
    ValidationSummary,
    build_plan,
)
from ontobq.orchestrate.validate import (
    LAYER_INTEGRITY,
    LAYER_LOAD,
    LAYER_METADATA,
    LAYER_SEMANTICS,
    USAGE_CODE,
    ValidationResult,
    validate_domain,
)

__all__ = [
    "LAYER_INTEGRITY",
    "LAYER_LOAD",
    "LAYER_METADATA",
    "LAYER_SEMANTICS",
    "USAGE_CODE",
    "ApplyResult",
    "ArtifactApplyStatus",
    "DeploymentPlan",
    "DomainIdentity",
    "PlanArtifact",
    "PlanBlockedError",
    "ValidationResult",
    "ValidationSummary",
    "apply_plan",
    "build_plan",
    "validate_domain",
]
