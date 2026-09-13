-- Isolated dirty rows for OBQ205.
-- customer_id cust_missing is absent from happy-path e2e_customers.
-- Unique order_id; Order and PLACED share this table (no OBQ206 same-table join).
-- Do not INSERT into e2e_orders.

CREATE OR REPLACE TABLE `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_obq205` AS
SELECT * FROM UNNEST([
  STRUCT(
    'ord_orphan_from' AS order_id,
    'cust_missing' AS customer_id,
    DATETIME '2024-01-15 10:00:00' AS created_at,
    'open' AS status
  )
]);
