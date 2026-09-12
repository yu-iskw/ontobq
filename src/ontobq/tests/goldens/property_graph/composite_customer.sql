CREATE OR REPLACE PROPERTY GRAPH `my-project.semantic.commerce_graph`
NODE TABLES (
  `my-project.semantic._ontobq_commerce_n_customer`
    AS Customer
    KEY (tenantId, id)
    LABEL Customer
    PROPERTIES (tenantId, id)
);
