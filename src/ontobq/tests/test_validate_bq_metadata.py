"""OBQ101-OBQ105 BigQuery metadata validation against Domain IR fixtures."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from ontobq.bigquery.fake import FakeBigQueryInspector, FakeCatalog
from ontobq.bigquery.inspector import (
    BigQueryInspector,
    ClientInspector,
    ColumnSnapshot,
    ScalarDryRunResult,
    SourceSnapshot,
    canonicalize_bq_type,
    canonicalize_location,
    scalar_expression_dry_run_sql,
)
from ontobq.diagnostics import Diagnostic, Severity
from ontobq.load import load_domain
from ontobq.tests.paths import FIXTURES_DIR
from ontobq.validate.bq_metadata import (
    OBQ101,
    OBQ102,
    OBQ103,
    OBQ104,
    OBQ105,
    validate_bigquery_metadata,
)

_CUSTOMERS = "my-project.raw.customers"
_ORDERS = "my-project.raw.orders"
_TARGET = "my-project.semantic"
_CUSTOMER_COLUMNS = (
    ColumnSnapshot("customer_id", "STRING", "REQUIRED"),
    ColumnSnapshot("customer_name", "STRING", "NULLABLE"),
    ColumnSnapshot("country", "STRING", "NULLABLE"),
    ColumnSnapshot("other_id", "STRING", "NULLABLE"),
    ColumnSnapshot("tenant_id", "STRING", "REQUIRED"),
)
_ORDER_COLUMNS = (
    ColumnSnapshot("order_id", "STRING", "REQUIRED"),
    ColumnSnapshot("customer_id", "STRING", "NULLABLE"),
    ColumnSnapshot("created_at", "TIMESTAMP", "NULLABLE"),
    ColumnSnapshot("status", "STRING", "NULLABLE"),
)


def _matching_catalog() -> FakeCatalog:
    return FakeCatalog(
        sources={
            _CUSTOMERS: SourceSnapshot(_CUSTOMERS, True, "TABLE", "US"),
            _ORDERS: SourceSnapshot(_ORDERS, True, "TABLE", "US"),
        },
        columns={_CUSTOMERS: _CUSTOMER_COLUMNS, _ORDERS: _ORDER_COLUMNS},
        locations={_TARGET: "US"},
        dry_runs={
            (_ORDERS, "TIMESTAMP(created_at)"): ScalarDryRunResult(True, "TIMESTAMP", None),
        },
    )


def _inspector(catalog: FakeCatalog | None = None) -> FakeBigQueryInspector:
    return FakeBigQueryInspector(_matching_catalog() if catalog is None else catalog)


def _codes(diagnostics: tuple[Diagnostic, ...]) -> tuple[str, ...]:
    return tuple(item.code for item in diagnostics)


def _paths_for(diagnostics: tuple[Diagnostic, ...], code: str) -> tuple[str, ...]:
    return tuple(item.path for item in diagnostics if item.code == code)


def test_commerce_matching_catalog_is_clean() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    assert validate_bigquery_metadata(domain, _inspector()) == ()


def test_expression_mapping_timestamp_dry_run_passes() -> None:
    domain = load_domain(FIXTURES_DIR / "expression-mapping.yaml")
    assert validate_bigquery_metadata(domain, _inspector()) == ()


def test_missing_source_is_obq101_and_skips_later_codes() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    diagnostics = validate_bigquery_metadata(domain, FakeBigQueryInspector())
    assert set(_codes(diagnostics)) == {OBQ101}
    assert _paths_for(diagnostics, OBQ101) == (
        "spec.entities.Customer.mapping.bigquery.source",
        "spec.entities.Order.mapping.bigquery.source",
        "spec.relationships.PLACED.mapping.bigquery.source",
    )


def test_unsupported_kind_is_obq101() -> None:
    catalog = _matching_catalog()
    sources = dict(catalog.sources)
    previous = sources[_CUSTOMERS]
    sources[_CUSTOMERS] = SourceSnapshot(previous.table_id, True, "EXTERNAL", previous.location)
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"),
        _inspector(FakeCatalog(sources, catalog.columns, catalog.locations, catalog.dry_runs)),
    )
    assert OBQ101 in _codes(diagnostics)
    assert "spec.entities.Customer.mapping.bigquery.source" in _paths_for(diagnostics, OBQ101)
    assert not any(
        item.path.startswith("spec.entities.Customer.mapping.bigquery.properties")
        for item in diagnostics
    )


def test_view_kind_is_supported() -> None:
    catalog = _matching_catalog()
    sources = dict(catalog.sources)
    previous = sources[_CUSTOMERS]
    sources[_CUSTOMERS] = SourceSnapshot(previous.table_id, True, "VIEW", previous.location)
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"),
        _inspector(FakeCatalog(sources, catalog.columns, catalog.locations, catalog.dry_runs)),
    )
    assert diagnostics == ()


def test_missing_property_column_is_obq102() -> None:
    catalog = _matching_catalog()
    columns = dict(catalog.columns)
    columns[_CUSTOMERS] = tuple(col for col in _CUSTOMER_COLUMNS if col.name != "country")
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"),
        _inspector(FakeCatalog(catalog.sources, columns, catalog.locations, catalog.dry_runs)),
    )
    assert _paths_for(diagnostics, OBQ102) == (
        "spec.entities.Customer.mapping.bigquery.properties.country",
    )
    assert OBQ104 not in _codes(diagnostics)


def test_missing_edge_key_column_is_obq102() -> None:
    catalog = _matching_catalog()
    columns = dict(catalog.columns)
    columns[_ORDERS] = tuple(col for col in _ORDER_COLUMNS if col.name != "order_id")
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"),
        _inspector(FakeCatalog(catalog.sources, columns, catalog.locations, catalog.dry_runs)),
    )
    assert "spec.relationships.PLACED.mapping.bigquery.key.0" in _paths_for(diagnostics, OBQ102)


def test_missing_endpoint_column_is_obq102() -> None:
    catalog = _matching_catalog()
    columns = dict(catalog.columns)
    columns[_ORDERS] = tuple(col for col in _ORDER_COLUMNS if col.name != "customer_id")
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"),
        _inspector(FakeCatalog(catalog.sources, columns, catalog.locations, catalog.dry_runs)),
    )
    assert "spec.relationships.PLACED.mapping.bigquery.from.id" in _paths_for(diagnostics, OBQ102)


def test_expression_dry_run_failure_is_obq103() -> None:
    catalog = _matching_catalog()
    dry_runs = {
        (_ORDERS, "TIMESTAMP(created_at)"): ScalarDryRunResult(False, None, "Unrecognized name"),
    }
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "expression-mapping.yaml"),
        _inspector(FakeCatalog(catalog.sources, catalog.columns, catalog.locations, dry_runs)),
    )
    assert _paths_for(diagnostics, OBQ103) == (
        "spec.entities.Order.mapping.bigquery.properties.createdAt",
    )
    assert OBQ104 not in _codes(diagnostics)


def _write_entity(tmp_path: Path, semantic: str, column: str) -> Path:
    path = tmp_path / "domain.yaml"
    path.write_text(
        (
            "apiVersion: ontobq.dev/v1alpha1\n"
            "kind: Domain\n"
            "metadata:\n"
            "  name: commerce\n"
            "spec:\n"
            "  bigquery:\n"
            "    project: my-project\n"
            "    dataset: semantic\n"
            "    graph: commerce_graph\n"
            "  entities:\n"
            "    Customer:\n"
            "      key: [id]\n"
            "      properties:\n"
            "        id:\n"
            f"          type: {semantic}\n"
            "          nullable: false\n"
            "      mapping:\n"
            "        bigquery:\n"
            f"          source: {_CUSTOMERS}\n"
            "          properties:\n"
            "            id:\n"
            f"              column: {column}\n"
        ),
        encoding="utf-8",
    )
    return path


def test_string_versus_integer_is_obq104(tmp_path: Path) -> None:
    domain = load_domain(_write_entity(tmp_path, "integer", "customer_id"))
    catalog = FakeCatalog(
        sources={_CUSTOMERS: SourceSnapshot(_CUSTOMERS, True, "TABLE", "US")},
        columns={_CUSTOMERS: (ColumnSnapshot("customer_id", "STRING", "REQUIRED"),)},
        locations={_TARGET: "US"},
    )
    diagnostics = validate_bigquery_metadata(domain, _inspector(catalog))
    assert _codes(diagnostics) == (OBQ104,)


def test_int64_versus_number_is_obq104(tmp_path: Path) -> None:
    domain = load_domain(_write_entity(tmp_path, "number", "amount"))
    catalog = FakeCatalog(
        sources={_CUSTOMERS: SourceSnapshot(_CUSTOMERS, True, "TABLE", "US")},
        columns={_CUSTOMERS: (ColumnSnapshot("amount", "INT64", "NULLABLE"),)},
        locations={_TARGET: "US"},
    )
    diagnostics = validate_bigquery_metadata(domain, _inspector(catalog))
    assert _codes(diagnostics) == (OBQ104,)


def test_timestamp_versus_datetime_is_obq104(tmp_path: Path) -> None:
    domain = load_domain(_write_entity(tmp_path, "datetime", "created_at"))
    catalog = FakeCatalog(
        sources={_CUSTOMERS: SourceSnapshot(_CUSTOMERS, True, "TABLE", "US")},
        columns={_CUSTOMERS: (ColumnSnapshot("created_at", "TIMESTAMP", "NULLABLE"),)},
        locations={_TARGET: "US"},
    )
    diagnostics = validate_bigquery_metadata(domain, _inspector(catalog))
    assert _codes(diagnostics) == (OBQ104,)


def test_number_accepts_float64_numeric_bignumeric(tmp_path: Path) -> None:
    domain = load_domain(_write_entity(tmp_path, "number", "amount"))
    for physical in ("FLOAT64", "NUMERIC", "BIGNUMERIC"):
        catalog = FakeCatalog(
            sources={_CUSTOMERS: SourceSnapshot(_CUSTOMERS, True, "TABLE", "US")},
            columns={_CUSTOMERS: (ColumnSnapshot("amount", physical, "NULLABLE"),)},
            locations={_TARGET: "US"},
        )
        assert validate_bigquery_metadata(domain, _inspector(catalog)) == ()


def test_integer_accepts_int64(tmp_path: Path) -> None:
    domain = load_domain(_write_entity(tmp_path, "integer", "customer_id"))
    catalog = FakeCatalog(
        sources={_CUSTOMERS: SourceSnapshot(_CUSTOMERS, True, "TABLE", "US")},
        columns={_CUSTOMERS: (ColumnSnapshot("customer_id", "INT64", "REQUIRED"),)},
        locations={_TARGET: "US"},
    )
    assert validate_bigquery_metadata(domain, _inspector(catalog)) == ()


def test_endpoint_int64_versus_node_key_string_is_obq104() -> None:
    catalog = _matching_catalog()
    columns = dict(catalog.columns)
    columns[_ORDERS] = (
        ColumnSnapshot("order_id", "STRING", "REQUIRED"),
        ColumnSnapshot("customer_id", "INT64", "NULLABLE"),
        ColumnSnapshot("created_at", "TIMESTAMP", "NULLABLE"),
        ColumnSnapshot("status", "STRING", "NULLABLE"),
    )
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"),
        _inspector(FakeCatalog(catalog.sources, columns, catalog.locations, catalog.dry_runs)),
    )
    assert "spec.relationships.PLACED.mapping.bigquery.from.id" in _paths_for(diagnostics, OBQ104)


def test_edge_key_has_no_obq104() -> None:
    catalog = _matching_catalog()
    columns = dict(catalog.columns)
    columns[_ORDERS] = (
        ColumnSnapshot("order_id", "INT64", "REQUIRED"),
        ColumnSnapshot("customer_id", "STRING", "NULLABLE"),
        ColumnSnapshot("created_at", "TIMESTAMP", "NULLABLE"),
        ColumnSnapshot("status", "STRING", "NULLABLE"),
    )
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"),
        _inspector(FakeCatalog(catalog.sources, columns, catalog.locations, catalog.dry_runs)),
    )
    key_paths = [item.path for item in diagnostics if item.path.endswith(".key.0")]
    assert not any(item.code == OBQ104 for item in diagnostics if item.path in key_paths)


def test_eu_versus_us_is_obq105() -> None:
    catalog = _matching_catalog()
    sources = dict(catalog.sources)
    previous = sources[_CUSTOMERS]
    sources[_CUSTOMERS] = SourceSnapshot(previous.table_id, True, "TABLE", "EU")
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"),
        _inspector(FakeCatalog(sources, catalog.columns, catalog.locations, catalog.dry_runs)),
    )
    assert "spec.entities.Customer.mapping.bigquery.source" in _paths_for(diagnostics, OBQ105)


def test_missing_target_location_is_obq105() -> None:
    catalog = _matching_catalog()
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"),
        _inspector(
            FakeCatalog(catalog.sources, catalog.columns, {_TARGET: None}, catalog.dry_runs)
        ),
    )
    assert OBQ105 in _codes(diagnostics)


def test_composite_keys_check_both_columns() -> None:
    catalog = _matching_catalog()
    columns = dict(catalog.columns)
    columns[_CUSTOMERS] = tuple(col for col in _CUSTOMER_COLUMNS if col.name != "tenant_id")
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "composite-key.yaml"),
        _inspector(FakeCatalog(catalog.sources, columns, catalog.locations, catalog.dry_runs)),
    )
    assert _paths_for(diagnostics, OBQ102) == (
        "spec.entities.Customer.mapping.bigquery.properties.tenantId",
    )


def test_unknown_entity_ref_skips_endpoint_type_and_does_not_emit_obq003() -> None:
    catalog = _matching_catalog()
    columns = dict(catalog.columns)
    columns[_CUSTOMERS] = (
        ColumnSnapshot("customer_id", "STRING", "REQUIRED"),
        ColumnSnapshot("other_id", "INT64", "NULLABLE"),
    )
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "unknown-entity-ref.yaml"),
        _inspector(FakeCatalog(catalog.sources, columns, catalog.locations, catalog.dry_runs)),
    )
    codes = _codes(diagnostics)
    assert "OBQ003" not in codes
    assert "spec.relationships.POINTS_AT.mapping.bigquery.from.id" not in _paths_for(
        diagnostics, OBQ104
    )
    assert OBQ101 not in codes
    assert OBQ102 not in codes


def test_diagnostics_are_deterministic() -> None:
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    inspector = FakeBigQueryInspector()
    first = validate_bigquery_metadata(domain, inspector)
    second = validate_bigquery_metadata(domain, inspector)
    assert first == second


def test_same_source_emits_per_mapping_site() -> None:
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"), FakeBigQueryInspector()
    )
    assert _paths_for(diagnostics, OBQ101).count("spec.entities.Order.mapping.bigquery.source") == 1
    assert (
        _paths_for(diagnostics, OBQ101).count("spec.relationships.PLACED.mapping.bigquery.source")
        == 1
    )


def test_case_insensitive_column_match() -> None:
    catalog = _matching_catalog()
    columns = dict(catalog.columns)
    columns[_CUSTOMERS] = (
        ColumnSnapshot("Customer_ID", "STRING", "REQUIRED"),
        ColumnSnapshot("customer_name", "STRING", "NULLABLE"),
        ColumnSnapshot("country", "STRING", "NULLABLE"),
    )
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"),
        _inspector(FakeCatalog(catalog.sources, columns, catalog.locations, catalog.dry_runs)),
    )
    assert not any("properties.id" in item.path for item in diagnostics)


def test_all_layer3_codes_are_errors() -> None:
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "commerce.yaml"), FakeBigQueryInspector()
    )
    assert diagnostics
    assert all(item.severity is Severity.ERROR for item in diagnostics)


def test_inspector_protocol_has_exactly_four_methods() -> None:
    methods = {
        name
        for name, value in vars(BigQueryInspector).items()
        if callable(value) and not name.startswith("_")
    }
    assert methods == {
        "get_source",
        "get_columns",
        "dry_run_scalar_expression",
        "get_location",
    }


def test_canonicalize_google_aliases() -> None:
    assert canonicalize_bq_type("INTEGER") == "INT64"
    assert canonicalize_bq_type("BOOLEAN") == "BOOL"
    assert canonicalize_bq_type("FLOAT") == "FLOAT64"
    assert canonicalize_location("us") == "US"
    assert canonicalize_location("us-central1") == "US-CENTRAL1"
    assert canonicalize_location("US") != canonicalize_location("us-central1")


def test_dry_run_sql_is_type_probe_without_row_read() -> None:
    sql = scalar_expression_dry_run_sql(_ORDERS, "TIMESTAMP(created_at)")
    assert "TIMESTAMP(created_at)" in sql
    assert "__ontobq_type_probe" in sql
    assert "WHERE FALSE" in sql
    assert f"FROM `{_ORDERS}`" in sql


class _NotFoundError(Exception):
    """Duck-typed missing-resource error."""


class _BadQueryError(Exception):
    """Duck-typed dry-run failure."""


class _JobConfig:
    """Duck-typed QueryJobConfig with dry-run flags."""

    def __init__(self, dry_run: bool = False, use_query_cache: bool = True) -> None:
        self.dry_run = dry_run
        self.use_query_cache = use_query_cache


class _RecordingClient:
    """In-memory BigQuery client that records lookups and dry-run SQL."""

    def __init__(self, job_schema: object | None = None) -> None:
        self.queries: list[str] = []
        self.job_configs: list[_JobConfig] = []
        self.table_lookups: list[str] = []
        self.dataset_lookups: list[str] = []
        self.row_reads = 0
        self._job_schema = (
            (SimpleNamespace(field_type="TIMESTAMP"),) if job_schema is None else job_schema
        )
        self.tables = {
            _ORDERS: SimpleNamespace(
                table_type="TABLE",
                location="US",
                schema=(
                    SimpleNamespace(name="order_id", field_type="STRING", mode="REQUIRED"),
                    SimpleNamespace(name="created_at", field_type="TIMESTAMP", mode="NULLABLE"),
                ),
            )
        }
        self.datasets = {_TARGET: SimpleNamespace(location="US")}

    def get_table(self, table_id: str) -> object:
        self.table_lookups.append(table_id)
        if table_id not in self.tables:
            raise _NotFoundError(table_id)
        return self.tables[table_id]

    def get_dataset(self, dataset_id: str) -> object:
        self.dataset_lookups.append(dataset_id)
        if dataset_id not in self.datasets:
            raise _NotFoundError(dataset_id)
        return self.datasets[dataset_id]

    def query(self, sql: str, job_config: object | None = None) -> object:
        self.queries.append(sql)
        if isinstance(job_config, _JobConfig):
            self.job_configs.append(job_config)
        return SimpleNamespace(schema=self._job_schema)


class _CountingInspector:
    """Delegating inspector that records lookup ids for cache assertions."""

    def __init__(self, inner: FakeBigQueryInspector) -> None:
        self._inner = inner
        self.source_ids: list[str] = []
        self.column_ids: list[str] = []
        self.location_ids: list[str] = []

    def get_source(self, table_id: str) -> SourceSnapshot:
        self.source_ids.append(table_id)
        return self._inner.get_source(table_id)

    def get_columns(self, table_id: str) -> tuple[ColumnSnapshot, ...]:
        self.column_ids.append(table_id)
        return self._inner.get_columns(table_id)

    def dry_run_scalar_expression(self, source: str, expression: str) -> ScalarDryRunResult:
        return self._inner.dry_run_scalar_expression(source, expression)

    def get_location(self, resource: str) -> str | None:
        self.location_ids.append(resource)
        return self._inner.get_location(resource)


def _client_inspector(client: _RecordingClient) -> ClientInspector:
    return ClientInspector(client, _NotFoundError, (_NotFoundError, _BadQueryError), _JobConfig)


def test_client_inspector_dry_run_records_probe_and_does_not_query_rows() -> None:
    client = _RecordingClient()
    inspector = _client_inspector(client)
    result = inspector.dry_run_scalar_expression(_ORDERS, "TIMESTAMP(created_at)")
    assert result.ok is True
    assert result.type == "TIMESTAMP"
    assert len(client.queries) == 1
    assert "WHERE FALSE" in client.queries[0]
    assert client.job_configs[0].dry_run is True
    assert client.job_configs[0].use_query_cache is False
    assert client.row_reads == 0


def test_schema_less_dry_run_is_not_ok() -> None:
    inspector = _client_inspector(_RecordingClient(job_schema=()))
    result = inspector.dry_run_scalar_expression(_ORDERS, "TIMESTAMP(created_at)")
    assert result.ok is False
    assert result.type is None
    assert result.error is not None


def test_schema_less_dry_run_emits_obq103_not_obq104() -> None:
    inspector = _client_inspector(_RecordingClient(job_schema=()))
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "expression-mapping.yaml"), inspector
    )
    assert _paths_for(diagnostics, OBQ103) == (
        "spec.entities.Order.mapping.bigquery.properties.createdAt",
    )
    assert OBQ104 not in _codes(diagnostics)


def test_empty_probe_type_emits_obq103_not_obq104() -> None:
    inspector = _client_inspector(_RecordingClient(job_schema=(SimpleNamespace(field_type=""),)))
    diagnostics = validate_bigquery_metadata(
        load_domain(FIXTURES_DIR / "expression-mapping.yaml"), inspector
    )
    assert OBQ103 in _codes(diagnostics)
    assert OBQ104 not in _codes(diagnostics)


def test_get_location_for_dataset_does_not_probe_table() -> None:
    client = _RecordingClient()
    location = _client_inspector(client).get_location(_TARGET)
    assert location == "US"
    assert not client.table_lookups
    assert client.dataset_lookups == [_TARGET]


def test_get_location_for_table_uses_table_path() -> None:
    client = _RecordingClient()
    location = _client_inspector(client).get_location(_ORDERS)
    assert location == "US"
    assert client.table_lookups == [_ORDERS]
    assert not client.dataset_lookups


def test_validate_caches_source_schema_and_target_location_within_one_call() -> None:
    counter = _CountingInspector(_inspector())
    diagnostics = validate_bigquery_metadata(load_domain(FIXTURES_DIR / "commerce.yaml"), counter)
    assert not diagnostics
    assert counter.source_ids.count(_CUSTOMERS) == 1
    assert counter.source_ids.count(_ORDERS) == 1
    assert counter.column_ids.count(_CUSTOMERS) == 1
    assert counter.column_ids.count(_ORDERS) == 1
    assert counter.location_ids == [_TARGET]


def test_validate_does_not_cache_inspector_lookups_across_calls() -> None:
    counter = _CountingInspector(_inspector())
    domain = load_domain(FIXTURES_DIR / "commerce.yaml")
    validate_bigquery_metadata(domain, counter)
    first_sources = len(counter.source_ids)
    first_locations = len(counter.location_ids)
    validate_bigquery_metadata(domain, counter)
    assert len(counter.source_ids) == first_sources + first_sources
    assert len(counter.location_ids) == first_locations + first_locations


def test_client_inspector_missing_table() -> None:
    inspector = _client_inspector(_RecordingClient())
    snapshot = inspector.get_source("missing.ds.table")
    assert snapshot.exists is False
    columns = inspector.get_columns("missing.ds.table")
    assert len(columns) == 0


def test_metadata_modules_are_not_compilers_or_integrity_scanners() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = ("CREATE OR REPLACE VIEW", "PROPERTY GRAPH", "GROUP BY")
    for relative in ("validate/bq_metadata.py", "bigquery/inspector.py", "bigquery/fake.py"):
        text = (root / relative).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text


def test_protocol_is_inspectable() -> None:
    assert inspect.isclass(BigQueryInspector)
