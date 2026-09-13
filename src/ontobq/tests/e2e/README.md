# OntoBQ BigQuery E2E (issue 17)

This suite is **evidence only**: YAML → four validation layers → `plan` → idempotent `apply` → hand-written GQL. No new public `ontobq` API.

**RFC [#8](https://github.com/yu-iskw/ontobq/issues/8) stays OPEN.** Do not use `Closes #8` / `Fixes #8`. If an RFC MVP bullet cannot be proven, file a follow-up issue and link it here. A human closes #8 later.

---

## Naming freeze — `OF` vs `LineItem`

```text
Customer
   |
 PLACED
   v
 Order
   |
 CONTAINS
   v
 OrderItem          # E2E entity. Unit goldens keep LineItem.
   |                # Do not edit src/ontobq/tests/fixtures/commerce.yaml.
 OF                 # Frozen identifier for OrderItem → Product.
   v                # RFC #8 is silent; do not rename to LineItemOf / HAS_PRODUCT.
 Product
```

| Item | Freeze |
| --- | --- |
| Domain `metadata.name` | `commerce_e2e` → views `_ontobq_commerce_e2e_n_*` / `_e_*` |
| Graph object | `${ONTOBQ_E2E_GRAPH}` default **`commerce_e2e_graph`** (must not collide with view names) |
| Composite key | OrderItem `[orderId, sku]`; `CONTAINS` and `OF` endpoints use the full tuple |
| Expression | `TIMESTAMP(created_at)` on Order.`createdAt` and PLACED.`placedAt` (non-key) |
| Source tables | Same dataset as the graph, prefix `e2e_*`. Never RFC `my-project.raw` |
| GQL labels | Semantic (`:Customer`, `:PLACED`, `:OrderItem`, `:OF`), never `_ontobq_*` |

---

## Environment gates (fail closed, **no DDL**)

Refuse to run unless **all** of these are set. Unset or mismatch ⇒ skip or fail-fast, **zero DDL**, never fall back to ADC’s project.

| Variable | Required | Role |
| --- | --- | --- |
| `ONTOBQ_E2E` | yes | Must be `1`. Pytest marker `e2e` is not enough alone. |
| `ONTOBQ_E2E_PROJECT` | yes | Live project id. Never RFC `my-project`. Never ADC default. |
| `ONTOBQ_E2E_DATASET` | yes | Test-scoped dataset that supports property graphs. |
| `ONTOBQ_E2E_ALLOWED_PROJECTS` | yes | Comma-separated allowlist. **Unset ⇒ skip/fail, never mutate.** |
| `ONTOBQ_E2E_GRAPH` | no | Graph Identifier. Default `commerce_e2e_graph` (`^[A-Za-z][A-Za-z0-9_]*$`). |
| `GOOGLE_APPLICATION_CREDENTIALS` / ADC | for live client | `google.cloud.bigquery.Client()` uses ADC, not `ONTOBQ_*`. No SA JSON in this repo. |

**Allowlist rules** (implement in `conftest.py`):

1. Split `ONTOBQ_E2E_ALLOWED_PROJECTS` on commas, trim, require `ONTOBQ_E2E_PROJECT` to be an **exact** member.
2. Documented dataset prefix (recommended extra, not a substitute for the project allowlist): dataset id starts with `ontobq_e2e`.
3. Unset allowlist → `pytest.skip` (or fail-fast) with **no** inspector/mutator construction.
4. Project not in allowlist → refuse, **no DDL**.
5. `make test` without `ONTOBQ_E2E=1` must not collect live mutations: register marker `e2e`, addopts `-m "not e2e"`, **and** path-skip `tests/e2e` in `dev/test_python.sh` (that script globs every `**/tests` under `src/`).

---

## IAM (document; do not invent extra roles in code)

Scope credentials to the **test dataset**, not the org.

Typical:

- Project: `roles/bigquery.jobUser` (run query/DDL jobs)
- Dataset: `roles/bigquery.dataEditor` (or equivalent) on `${ONTOBQ_E2E_DATASET}`

Must be enough to:

- create / replace / drop **this run’s** seed tables (`e2e_*`)
- inspect table metadata (layer 3)
- query source tables (layer 4)
- create / replace / drop mapping views `_ontobq_commerce_e2e_*`
- create / replace / drop property graph `${ONTOBQ_E2E_GRAPH}`
- run GQL / `GRAPH_TABLE` against that graph

No production credentials or production data in fixtures. Default PR `test.yml` stays unit-only (no GCP secrets). If CI later runs E2E, use a **separate** workflow (WIF or SA + allowlisted project/dataset), never the default PR job.

---

## Placeholder interpolation

YAML and SQL under `fixtures/` are **templates**. Tokens:

`${ONTOBQ_E2E_PROJECT}` `${ONTOBQ_E2E_DATASET}` `${ONTOBQ_E2E_GRAPH}`

They are illegal `BigQueryTableId` / Identifier values until replaced. `apply_plan` and the compilers do **not** interpolate. Substitute **before** `load_domain` / `ontobq validate|plan|apply`. Never apply RFC `my-project` to a live account.

```python
from string import Template

def materialize(text: str, project: str, dataset: str, graph: str = "commerce_e2e_graph") -> str:
    return Template(text).substitute(
        ONTOBQ_E2E_PROJECT=project,
        ONTOBQ_E2E_DATASET=dataset,
        ONTOBQ_E2E_GRAPH=graph,
    )
```

---

## Setup / teardown

Against **one** allowlisted project/dataset:

1. Gate env (above). Stop if not allowlisted.
2. Seed happy-path tables (`fixtures/seed.sql`). Fixed ids. No `CURRENT_TIMESTAMP`.
3. Happy path: interpolate `commerce_e2e.yaml` → validate layers 1–4 → `plan` → `apply` → second unchanged `apply` → GQL in `gql_queries.md`.
4. Negatives: create **isolated** dirty/schema tables → interpolate `invalid_obq*.yaml` → `validate --format json` → assert exact `diagnostics[].code` → **do not apply**.
5. Teardown **this run’s** objects only (`fixtures/teardown.sql`).

**Teardown order (required):**

1. `DROP PROPERTY GRAPH IF EXISTS` this run’s graph
2. `DROP VIEW IF EXISTS` this run’s `_ontobq_commerce_e2e_*` views
3. `DROP TABLE IF EXISTS` this run’s `e2e_*` seed and dirty tables

**Never `DROP DATASET`.** Apply does not delete objects removed from config; isolation must not assume a dataset wipe.

Apply-created objects (domain `commerce_e2e`, default graph `commerce_e2e_graph`):

| Kind | Name |
| --- | --- |
| Graph | `{project}.{dataset}.commerce_e2e_graph` |
| Node views | `_ontobq_commerce_e2e_n_customer`, `_n_order`, `_n_orderitem`, `_n_product` |
| Edge views | `_ontobq_commerce_e2e_e_placed`, `_e_contains`, `_e_of` |

---

## How to run

```bash
export ONTOBQ_E2E=1
export ONTOBQ_E2E_PROJECT=...               # must be in the allowlist
export ONTOBQ_E2E_DATASET=...               # property-graph capable; prefer prefix ontobq_e2e
export ONTOBQ_E2E_ALLOWED_PROJECTS=...      # comma-separated; unset => skip, no DDL
export ONTOBQ_E2E_GRAPH=commerce_e2e_graph   # optional
# ADC or GOOGLE_APPLICATION_CREDENTIALS with dataset-scoped IAM

make test-e2e
# or: ONTOBQ_E2E=1 uv run pytest -m e2e
```

`make test` / `make lint` stay offline-green without GCP.

---

## Fixture map

| File | Purpose |
| --- | --- |
| `fixtures/commerce_e2e.yaml` | Happy-path Domain (interpolate then load) |
| `fixtures/seed.sql` | Deterministic Customer / Order / OrderItem / Product rows |
| `fixtures/invalid_obq102.yaml` | Missing column `country_code` on `e2e_customers` |
| `fixtures/invalid_obq104.yaml` + `schema_obq104.sql` | string vs INT64 `country` on isolated table |
| `fixtures/invalid_obq202.yaml` + `dirty_obq202.sql` | Duplicate Customer key |
| `fixtures/invalid_obq204.yaml` + `dirty_obq204.sql` | Duplicate PLACED key (split node/edge tables) |
| `fixtures/invalid_obq205.yaml` + `dirty_obq205.sql` | Orphan PLACED `from` |
| `fixtures/invalid_obq206.yaml` + `dirty_obq206.sql` | Orphan PLACED `to` (split sources; required) |
| `fixtures/teardown.sql` | Graph → views → tables; never DROP DATASET |
| `gql_queries.md` | Single-hop, multi-hop, composite-key GQL + expected rows |

Integrity queries **source** tables. GQL hits **views + graph**. Do not poison happy-path seed tables. Assert exact diagnostic codes, not message substrings.

---

## GQL dialect freeze

Hand-written queries only. Compilers do not emit `MATCH`.

- **Default:** `SELECT … FROM GRAPH_TABLE(graph MATCH … RETURN …)` via `GoogleBigQueryReadExecutor.query`.
- **Scalar `RETURN` only.** Do not `RETURN` graph elements or `TO_JSON(n)` for pytest rows.
- **Do not use** `GRAPH_EXPAND` (not GQL; does not prove RFC #8 bullet 6).
- Empty `{}` property filters are illegal. Do not write `(b {id: a.id})` on a later node; use `WHERE`.
- Omitted edge `PROPERTIES` in DDL still means all view columns (including `__ontobq_*`). E2E must not assert helper names; a `NO PROPERTIES` fix is a `#14` follow-up.
- Top-level `GRAPH … MATCH` is a fallback only if GRAPH_TABLE is rejected; document any switch here.
- Backtick-quote reserved labels: `` :`Order` ``, `` :`CONTAINS` ``, `` :`OF` ``. Unquoted `:Customer`, `:PLACED`, `:OrderItem`, `:Product`.
- Gold query + rows: `gql.py` and `gql_queries.md`. GQL needs a BigQuery **Enterprise or Enterprise Plus** reservation.

---

## RFC #8 MVP bullets (prove or file a gap; RFC stays OPEN)

On `origin/main`, bullets 1–5 are **unit-proven** (fakes/goldens). This suite must still prove **live**:

| RFC bullet | Live proof this package owns |
| --- | --- |
| 1 layers 3–4 | `test_mvp_happy_path.py` against real catalog/source tables |
| 2 plan-after-apply | `test_mvp_determinism.py` |
| 3–4 apply / reapply | session `apply_plan` + second apply via `GoogleMutationExecutor` |
| 5 exact codes, zero DDL | `test_mvp_negative.py` `OBQ102/104/202/204/205/206` + recording mutator |
| 6 GQL (absent on main) | GRAPH_TABLE single-hop + Customer→…→Product multi-hop; composite OrderItem |

If live graph DDL disagrees with `#14` goldens, file a follow-up — do not expand the ontology here. **Leave RFC #8 open.**
