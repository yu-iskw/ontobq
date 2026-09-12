CREATE OR REPLACE VIEW `my-project.semantic._ontobq_commerce_e_placed` AS
SELECT
  order_id AS __ontobq_edge_key_0,
  customer_id AS __ontobq_from_id,
  order_id AS __ontobq_to_id,
  created_at AS placedAt
FROM `my-project.raw.orders`;
