CREATE OR REPLACE VIEW `my-project.semantic._ontobq_commerce_n_order` AS
SELECT
  order_id AS id,
  created_at AS createdAt,
  status AS status
FROM `my-project.raw.orders`;
