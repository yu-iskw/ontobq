CREATE OR REPLACE PROPERTY GRAPH `my-project.semantic.commerce_graph`
NODE TABLES (
  `my-project.semantic._ontobq_commerce_n_customer`
    AS Customer
    KEY (id)
    LABEL Customer
    PROPERTIES (id, name, country),
  `my-project.semantic._ontobq_commerce_n_order`
    AS Order
    KEY (id)
    LABEL Order
    PROPERTIES (id, createdAt, status)
)
EDGE TABLES (
  `my-project.semantic._ontobq_commerce_e_placed`
    AS PLACED
    KEY (__ontobq_edge_key_0)
    SOURCE KEY (__ontobq_from_id)
      REFERENCES Customer (id)
    DESTINATION KEY (__ontobq_to_id)
      REFERENCES Order (id)
    LABEL PLACED
    PROPERTIES (placedAt)
);
