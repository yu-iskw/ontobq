-- Isolated dirty rows for OBQ206 (orphan destination).
-- Edge order_id ord_ghost is absent from happy-path e2e_orders (Order source).
-- customer_id cust_ada exists on e2e_customers (no OBQ205).
-- Unique edge key (no OBQ204).
-- Split sources are required: commerce PLACED goldens join the same table to itself.
-- Do not INSERT into e2e_orders.

CREATE OR REPLACE TABLE `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_edge_obq206` AS
SELECT * FROM UNNEST([
  STRUCT(
    'ord_ghost' AS order_id,
    'cust_ada' AS customer_id,
    DATETIME '2024-01-15 10:00:00' AS created_at,
    'open' AS status
  )
]);
