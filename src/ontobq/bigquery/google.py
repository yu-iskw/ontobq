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

"""Google Cloud BigQuery adapter. The only production module that imports google.cloud."""

from __future__ import annotations

import importlib
from typing import Any, cast

from ontobq.bigquery.inspector import ClientInspector, SdkShapedClient

__all__ = ["GoogleBigQueryInspector"]


def _load_bigquery() -> Any:
    return importlib.import_module("google.cloud.bigquery")


def _load_exceptions() -> Any:
    return importlib.import_module("google.api_core.exceptions")


def _sdk_client(client: object | None, sdk: Any) -> SdkShapedClient:
    if client is not None:
        return cast("SdkShapedClient", client)
    return cast("SdkShapedClient", sdk.Client())


class GoogleBigQueryInspector(ClientInspector):
    """Read-only metadata inspector backed by ``google.cloud.bigquery.Client``."""

    def __init__(self, client: object | None = None) -> None:
        sdk = _load_bigquery()
        errors = _load_exceptions()
        super().__init__(
            _sdk_client(client, sdk),
            errors.NotFound,
            (errors.BadRequest, errors.NotFound),
            sdk.QueryJobConfig,
        )
