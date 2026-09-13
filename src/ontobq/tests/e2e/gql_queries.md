# Hand-written GQL for the issue 17 commerce E2E seed

Copy to `src/ontobq/tests/e2e/gql_queries.md`. RFC [#8](https://github.com/yu-iskw/ontobq/issues/8) stays **OPEN**.

Compilers do **not** emit `MATCH` / `GRAPH_TABLE`. These queries are suite-owned.

**Dialect freeze:** BigQuery currently accepts both `GRAPH_TABLE` (GoogleSQL) and a top-level `GRAPH … MATCH` GQL query. Gold **query + result rows** against the test project in the #17 PR. If live grammar disagrees with `#14` DDL goldens, open a `#14` follow-up — do not expand the ontology here.

Use **semantic labels** (`:Customer`, `:PLACED`, `:OrderItem`, `:OF`), never `_ontobq_*` view ids.

Substitute `${ONTOBQ_E2E_PROJECT}`, `${ONTOBQ_E2E_DATASET}`, `${ONTOBQ_E2E_GRAPH}` (default graph `commerce_e2e_graph`) before running. Compare timestamps as `TIMESTAMP`, not `CURRENT_TIMESTAMP`, and not brittle `CAST(… AS STRING)` formatting.

Seed ids are fixed in `fixtures/seed.sql`.

---

## Expected timestamps (expression `TIMESTAMP(created_at)`)

`created_at` is `DATETIME`; the mapping expression is `TIMESTAMP(created_at)` (UTC).

| order_id   | createdAt / placedAt                 |
| ---------- | ------------------------------------ |
| `ord_1001` | `TIMESTAMP '2024-01-15 10:00:00+00'` |
| `ord_1002` | `TIMESTAMP '2024-02-01 12:30:00+00'` |
| `ord_2001` | `TIMESTAMP '2024-03-10 08:00:00+00'` |

---

## 1. Single-hop: `(:Customer)-[:PLACED]->(:Order)`

### GRAPH_TABLE variant (single-hop)

```sql
SELECT
  customer_id,
  order_id,
  status
FROM GRAPH_TABLE(
  `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.${ONTOBQ_E2E_GRAPH}`
  MATCH (c:Customer)-[:PLACED]->(o:Order)
  RETURN c.id AS customer_id, o.id AS order_id, o.status AS status
)
ORDER BY customer_id, order_id;
```

### GRAPH MATCH variant (single-hop)

```sql
GRAPH `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.${ONTOBQ_E2E_GRAPH}`
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN c.id AS customer_id, o.id AS order_id, o.status AS status
ORDER BY customer_id, order_id
```

### Expected rows (3)

| customer_id | order_id   | status    |
| ----------- | ---------- | --------- |
| `cust_ada`  | `ord_1001` | `open`    |
| `cust_ada`  | `ord_1002` | `shipped` |
| `cust_bob`  | `ord_2001` | `open`    |

---

## 2. Multi-hop: Customer → Order → OrderItem → Product

Required RFC / issue 17 evidence: at least one deterministic multi-hop result.

### GRAPH_TABLE variant (multi-hop)

```sql
SELECT
  customer_id,
  order_id,
  sku,
  quantity,
  product_id,
  product_name
FROM GRAPH_TABLE(
  `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.${ONTOBQ_E2E_GRAPH}`
  MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(i:OrderItem)-[:OF]->(p:Product)
  RETURN
    c.id AS customer_id,
    o.id AS order_id,
    i.sku AS sku,
    i.quantity AS quantity,
    p.id AS product_id,
    p.name AS product_name
)
ORDER BY customer_id, order_id, sku;
```

### GRAPH MATCH variant (multi-hop)

```sql
GRAPH `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.${ONTOBQ_E2E_GRAPH}`
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(i:OrderItem)-[:OF]->(p:Product)
RETURN
  c.id AS customer_id,
  o.id AS order_id,
  i.sku AS sku,
  i.quantity AS quantity,
  p.id AS product_id,
  p.name AS product_name
ORDER BY customer_id, order_id, sku
```

### Expected rows (4)

| customer_id | order_id   | sku     | quantity | product_id      | product_name |
| ----------- | ---------- | ------- | -------- | --------------- | ------------ |
| `cust_ada`  | `ord_1001` | `SKU_G` | 1        | `prod_gadget`   | `Gadget`     |
| `cust_ada`  | `ord_1001` | `SKU_W` | 2        | `prod_widget`   | `Widget`     |
| `cust_ada`  | `ord_1002` | `SKU_W` | 4        | `prod_widget`   | `Widget`     |
| `cust_bob`  | `ord_2001` | `SKU_S` | 3        | `prod_sprocket` | `Sprocket`   |

Ada → `ord_1001` → (`ord_1001`, `SKU_W`) → Widget is the smallest complete 4-hop path.

---

## 3. Composite key live: OrderItem `(orderId, sku)` + `OF`

Proves two OrderItems can share `SKU_W` under different `orderId` values, and `OF` uses the full OrderItem key as the source endpoint.

### GRAPH_TABLE variant (composite key)

```sql
SELECT
  order_id,
  sku,
  product_id
FROM GRAPH_TABLE(
  `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.${ONTOBQ_E2E_GRAPH}`
  MATCH (i:OrderItem)-[:OF]->(p:Product)
  WHERE i.sku = 'SKU_W'
  RETURN i.orderId AS order_id, i.sku AS sku, p.id AS product_id
)
ORDER BY order_id, sku;
```

### GRAPH MATCH variant (composite key)

```sql
GRAPH `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.${ONTOBQ_E2E_GRAPH}`
MATCH (i:OrderItem)-[:OF]->(p:Product)
FILTER i.sku = 'SKU_W'
RETURN i.orderId AS order_id, i.sku AS sku, p.id AS product_id
ORDER BY order_id, sku
```

(`WHERE` vs `FILTER`: freeze whichever the test project accepts.)

### Expected rows (2) — same SKU, distinct composite keys

| order_id   | sku     | product_id    |
| ---------- | ------- | ------------- |
| `ord_1001` | `SKU_W` | `prod_widget` |
| `ord_1002` | `SKU_W` | `prod_widget` |

Pin one row:

```sql
MATCH (i:OrderItem {orderId: 'ord_1001', sku: 'SKU_W'})-[:OF]->(p:Product)
RETURN i.orderId, i.sku, p.id
```

Expected: `ord_1001`, `SKU_W`, `prod_widget`.

---

## 4. Filtered single customer (sanity)

```sql
SELECT customer_id, order_id
FROM GRAPH_TABLE(
  `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.${ONTOBQ_E2E_GRAPH}`
  MATCH (c:Customer {id: 'cust_bob'})-[:PLACED]->(o:Order)
  RETURN c.id AS customer_id, o.id AS order_id
);
```

Expected: one row `cust_bob`, `ord_2001`.

---

## Assert in tests

- Exact column values from the tables above (order rows with `ORDER BY`).
- Assert **semantic** names in the query text (`Customer`, `PLACED`, `OrderItem`, `OF`).
- Do not query `_ontobq_commerce_e2e_n_customer` for RFC multi-hop evidence (views are an implementation detail).
