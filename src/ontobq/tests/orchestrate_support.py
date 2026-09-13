"""Shared Fake BigQuery catalogs for orchestration tests. Not mocks."""

from __future__ import annotations

from ontobq.bigquery.fake import FakeBigQueryInspector, FakeCatalog
from ontobq.bigquery.inspector import ColumnSnapshot, ScalarDryRunResult, SourceSnapshot
from ontobq.bq import FakeBigQueryReadExecutor, QueryEstimate

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


def commerce_catalog() -> FakeCatalog:
    """Physical catalog that matches the commerce / expression / composite fixtures."""

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


def commerce_inspector() -> FakeBigQueryInspector:
    return FakeBigQueryInspector(commerce_catalog())


def clean_executor() -> FakeBigQueryReadExecutor:
    return FakeBigQueryReadExecutor()


def catalog_without_country() -> FakeCatalog:
    catalog = commerce_catalog()
    columns = dict(catalog.columns)
    columns[_CUSTOMERS] = tuple(col for col in _CUSTOMER_COLUMNS if col.name != "country")
    return FakeCatalog(catalog.sources, columns, catalog.locations, catalog.dry_runs)


class FailingInspector:
    """Probe inspector: any call is a test failure. Not a mock library patch."""

    def get_source(self, table_id: str) -> SourceSnapshot:
        raise AssertionError(f"inspector must not be called for {table_id}")

    def get_columns(self, table_id: str) -> tuple[ColumnSnapshot, ...]:
        raise AssertionError(f"inspector must not be called for {table_id}")

    def dry_run_scalar_expression(self, source: str, expression: str) -> ScalarDryRunResult:
        raise AssertionError(f"inspector must not be called for {source} {expression}")

    def get_location(self, resource: str) -> str | None:
        raise AssertionError(f"inspector must not be called for {resource}")


class FailingExecutor:
    """Probe executor: any call is a test failure."""

    def dry_run(self, sql: str) -> QueryEstimate:
        raise AssertionError(f"executor must not dry-run {sql[:32]}")

    def query(self, sql: str, *, max_rows: int) -> tuple[object, ...]:
        raise AssertionError(f"executor must not query {sql[:32]} max_rows={max_rows}")
