CREATE OR REPLACE VIEW `my-project.semantic._ontobq_commerce_n_customer` AS
SELECT
  tenant_id AS tenantId,
  customer_id AS id
FROM `my-project.raw.customers`;
