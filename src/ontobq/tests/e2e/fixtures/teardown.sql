-- Teardown THIS RUN'S objects only. Never DROP DATASET.
-- Order: property graph → mapping views → seed tables (happy-path then isolated negatives).
-- Substitute ${ONTOBQ_E2E_PROJECT} ${ONTOBQ_E2E_DATASET} ${ONTOBQ_E2E_GRAPH} first.
-- Default graph identifier: commerce_e2e_graph
-- #16 apply does not delete objects removed from config; E2E owns cleanup.

-- 1. Graph (depends on views)
DROP PROPERTY GRAPH IF EXISTS
  `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.${ONTOBQ_E2E_GRAPH}`;

-- 2. Mapping views (domain commerce_e2e)
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_n_customer`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_n_order`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_n_orderitem`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_n_product`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_e_placed`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_e_contains`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_e_of`;

-- 3. Happy-path seed tables
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_order_items`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_products`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_customers`;

-- 4. Isolated negative tables (do not exist unless those SQL files ran)
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_customers_obq104`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_customers_obq202`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_obq204`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_obq204_nodes`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_obq205`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_edge_obq206`;

-- Do NOT: DROP SCHEMA / DROP DATASET
