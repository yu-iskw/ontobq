CREATE OR REPLACE VIEW `my-project.semantic._ontobq_commerce_e_contains` AS
SELECT
  order_id AS __ontobq_edge_key_0,
  sku AS __ontobq_edge_key_1,
  order_id AS __ontobq_from_id,
  order_id AS __ontobq_to_orderId,
  sku AS __ontobq_to_sku
FROM `my-project.raw.order_items`;
