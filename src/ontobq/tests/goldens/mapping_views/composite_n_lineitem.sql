CREATE OR REPLACE VIEW `my-project.semantic._ontobq_commerce_n_lineitem` AS
SELECT
  order_id AS orderId,
  sku AS sku,
  qty AS quantity
FROM `my-project.raw.order_items`;
