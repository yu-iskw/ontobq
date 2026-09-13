-- Isolated schema for OBQ104. country is INT64; Domain still declares string (no CAST).
-- Do not alter e2e_customers.

CREATE OR REPLACE TABLE `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_customers_obq104` AS
SELECT * FROM UNNEST([
  STRUCT('cust_ada' AS customer_id, 'Ada Lovelace' AS customer_name, 840 AS country)
]);
