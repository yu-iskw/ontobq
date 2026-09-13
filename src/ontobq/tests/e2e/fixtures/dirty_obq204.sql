-- Isolated dirty rows for OBQ204.
-- Edge table: two rows with the same order_id (duplicate PLACED key).
-- Node table: one row with that order_id so Order keys stay unique (no OBQ202).
-- from.customer_id = cust_ada exists on happy-path e2e_customers (no OBQ205).
-- Do not INSERT into e2e_orders.

CREATE OR REPLACE TABLE `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_obq204` AS
SELECT * FROM UNNEST([
  STRUCT(
    'ord_dup' AS order_id,
    'cust_ada' AS customer_id,
    DATETIME '2024-01-15 10:00:00' AS created_at,
    'open' AS status
  ),
  STRUCT(
    'ord_dup' AS order_id,
    'cust_ada' AS customer_id,
    DATETIME '2024-01-15 10:00:00' AS created_at,
    'open' AS status
  )
]);

CREATE OR REPLACE TABLE `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_obq204_nodes` AS
SELECT * FROM UNNEST([
  STRUCT(
    'ord_dup' AS order_id,
    'cust_ada' AS customer_id,
    DATETIME '2024-01-15 10:00:00' AS created_at,
    'open' AS status
  )
]);
