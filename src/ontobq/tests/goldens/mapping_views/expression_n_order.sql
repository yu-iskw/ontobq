CREATE OR REPLACE VIEW `my-project.semantic._ontobq_commerce_n_order` AS
SELECT
  order_id AS id,
  TIMESTAMP(created_at) AS createdAt
FROM `my-project.raw.orders`;
