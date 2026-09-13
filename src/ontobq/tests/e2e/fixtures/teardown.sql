-- Teardown THIS RUN'S objects only. Never DROP DATASET.
-- Order: property graph → mapping views → seed tables (happy-path then isolated negatives).
-- Substitute ${ONTOBQ_E2E_PROJECT} ${ONTOBQ_E2E_DATASET} ${ONTOBQ_E2E_GRAPH} ${ONTOBQ_E2E_RUN_ID} first.
-- Default graph identifier: commerce_e2e_graph_${ONTOBQ_E2E_RUN_ID}
-- ${ONTOBQ_E2E_RUN_ID} suffix scopes every dropped object to this session only.
-- #16 apply does not delete objects removed from config; E2E owns cleanup.

-- 1. Graph (depends on views)
DROP PROPERTY GRAPH IF EXISTS
  `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.${ONTOBQ_E2E_GRAPH}`;

-- 2. Mapping views (domain commerce_e2e_${ONTOBQ_E2E_RUN_ID})
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_${ONTOBQ_E2E_RUN_ID}_n_customer`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_${ONTOBQ_E2E_RUN_ID}_n_order`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_${ONTOBQ_E2E_RUN_ID}_n_orderitem`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_${ONTOBQ_E2E_RUN_ID}_n_product`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_${ONTOBQ_E2E_RUN_ID}_e_placed`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_${ONTOBQ_E2E_RUN_ID}_e_contains`;
DROP VIEW IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}._ontobq_commerce_e2e_${ONTOBQ_E2E_RUN_ID}_e_of`;

-- 3. Happy-path seed tables
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_order_items_${ONTOBQ_E2E_RUN_ID}`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_${ONTOBQ_E2E_RUN_ID}`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_products_${ONTOBQ_E2E_RUN_ID}`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_customers_${ONTOBQ_E2E_RUN_ID}`;

-- 4. Isolated negative tables (do not exist unless those SQL files ran)
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_customers_obq104_${ONTOBQ_E2E_RUN_ID}`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_customers_obq202_${ONTOBQ_E2E_RUN_ID}`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_obq204_${ONTOBQ_E2E_RUN_ID}`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_obq204_nodes_${ONTOBQ_E2E_RUN_ID}`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_obq205_${ONTOBQ_E2E_RUN_ID}`;
DROP TABLE IF EXISTS `${ONTOBQ_E2E_PROJECT}.${ONTOBQ_E2E_DATASET}.e2e_orders_edge_obq206_${ONTOBQ_E2E_RUN_ID}`;

-- Do NOT: DROP SCHEMA / DROP DATASET
