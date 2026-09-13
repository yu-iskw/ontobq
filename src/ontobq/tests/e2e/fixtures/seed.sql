-- TEMPLATE — substitute ${ONTOBQ_E2E_PROJECT} ${ONTOBQ_E2E_DATASET} ${ONTOBQ_E2E_RUN_ID} before running.
-- Happy-path seed only. Do not INSERT integrity-negative rows here.
-- Fixed ids. No CURRENT_TIMESTAMP (GQL expected rows must be stable).
-- created_at is DATETIME so Order.createdAt / PLACED.placedAt expression TIMESTAMP(created_at) is real work.
-- Tables live in the E2E dataset (not RFC my-project.raw). Never DROP DATASET.
-- ${ONTOBQ_E2E_RUN_ID} suffix keeps parallel sessions from overwriting each other's tables.

CREATE OR REPLACE TABLE `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_customers_${ONTOBQ_E2E_RUN_ID}` AS
SELECT * FROM UNNEST([
  STRUCT('cust_ada' AS customer_id, 'Ada Lovelace' AS customer_name, 'US' AS country),
  STRUCT('cust_bob' AS customer_id, 'Bob Martinez' AS customer_name, 'JP' AS country)
]);

CREATE OR REPLACE TABLE `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_${ONTOBQ_E2E_RUN_ID}` AS
SELECT * FROM UNNEST([
  STRUCT(
    'ord_1001' AS order_id,
    'cust_ada' AS customer_id,
    DATETIME '2024-01-15 10:00:00' AS created_at,
    'open' AS status
  ),
  STRUCT(
    'ord_1002' AS order_id,
    'cust_ada' AS customer_id,
    DATETIME '2024-02-01 12:30:00' AS created_at,
    'shipped' AS status
  ),
  STRUCT(
    'ord_2001' AS order_id,
    'cust_bob' AS customer_id,
    DATETIME '2024-03-10 08:00:00' AS created_at,
    'open' AS status
  )
]);

CREATE OR REPLACE TABLE `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_products_${ONTOBQ_E2E_RUN_ID}` AS
SELECT * FROM UNNEST([
  STRUCT('prod_widget' AS product_id, 'Widget' AS product_name),
  STRUCT('prod_gadget' AS product_id, 'Gadget' AS product_name),
  STRUCT('prod_sprocket' AS product_id, 'Sprocket' AS product_name)
]);

CREATE OR REPLACE TABLE `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_order_items_${ONTOBQ_E2E_RUN_ID}` AS
SELECT * FROM UNNEST([
  STRUCT(
    'ord_1001' AS order_id,
    'SKU_W' AS sku,
    'prod_widget' AS product_id,
    2 AS qty
  ),
  STRUCT(
    'ord_1001' AS order_id,
    'SKU_G' AS sku,
    'prod_gadget' AS product_id,
    1 AS qty
  ),
  STRUCT(
    'ord_1002' AS order_id,
    'SKU_W' AS sku,
    'prod_widget' AS product_id,
    4 AS qty
  ),
  STRUCT(
    'ord_2001' AS order_id,
    'SKU_S' AS sku,
    'prod_sprocket' AS product_id,
    3 AS qty
  )
]);
