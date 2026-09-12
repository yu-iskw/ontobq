CREATE OR REPLACE VIEW `my-project.semantic._ontobq_commerce_n_customer` AS
SELECT
  customer_id AS id,
  TRIM(customer_name) AS name,
  country AS country
FROM `my-project.raw.customers`;
