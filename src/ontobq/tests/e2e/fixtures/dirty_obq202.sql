-- Isolated dirty rows for OBQ202. Duplicate customer_id. Do not INSERT into e2e_customers.
-- ${ONTOBQ_E2E_RUN_ID} suffix keeps this run's table isolated.

CREATE OR REPLACE TABLE `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_customers_obq202_${ONTOBQ_E2E_RUN_ID}` AS
SELECT * FROM UNNEST([
  STRUCT('dup_cust' AS customer_id, 'One' AS customer_name, 'US' AS country),
  STRUCT('dup_cust' AS customer_id, 'Two' AS customer_name, 'CA' AS country)
]);
