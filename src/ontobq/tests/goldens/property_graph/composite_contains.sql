CREATE OR REPLACE PROPERTY GRAPH `my-project.semantic.commerce_graph`
NODE TABLES (
  `my-project.semantic._ontobq_commerce_n_order`
    AS Order
    KEY (id)
    LABEL Order
    PROPERTIES (id),
  `my-project.semantic._ontobq_commerce_n_lineitem`
    AS LineItem
    KEY (orderId, sku)
    LABEL LineItem
    PROPERTIES (orderId, sku, quantity)
)
EDGE TABLES (
  `my-project.semantic._ontobq_commerce_e_contains`
    AS CONTAINS
    KEY (__ontobq_edge_key_0, __ontobq_edge_key_1)
    SOURCE KEY (__ontobq_from_id)
      REFERENCES Order (id)
    DESTINATION KEY (__ontobq_to_orderId, __ontobq_to_sku)
      REFERENCES LineItem (orderId, sku)
    LABEL CONTAINS
);
