# Copyright 2025 yu-iskw
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Hand-written GRAPH_TABLE queries and expected rows. Compilers do not emit GQL."""

from __future__ import annotations

from ontobq.sql.interpolate import quote_resource

# Dialect freeze: GRAPH_TABLE + MATCH + RETURN (see gql_queries.md / issue-17-gql-dialect).
# Quote reserved labels: Order, CONTAINS, OF.

_SINGLE_HOP = """\
SELECT customer_id, order_id, status
FROM GRAPH_TABLE(
  {graph}
  MATCH (c:Customer)-[:PLACED]->(o:`Order`)
  RETURN c.id AS customer_id, o.id AS order_id, o.status AS status
)
ORDER BY customer_id, order_id
"""

_MULTI_HOP = """\
SELECT customer_id, order_id, sku, quantity, product_id, product_name
FROM GRAPH_TABLE(
  {graph}
  MATCH (c:Customer)-[:PLACED]->(o:`Order`)-[:`CONTAINS`]->(i:OrderItem)-[:`OF`]->(p:Product)
  RETURN
    c.id AS customer_id,
    o.id AS order_id,
    i.sku AS sku,
    i.quantity AS quantity,
    p.id AS product_id,
    p.name AS product_name
)
ORDER BY customer_id, order_id, sku
"""

_COMPOSITE_ITEMS = """\
SELECT order_id, sku, product_id
FROM GRAPH_TABLE(
  {graph}
  MATCH (i:OrderItem)-[:`OF`]->(p:Product)
  WHERE i.sku = 'SKU_W'
  RETURN i.orderId AS order_id, i.sku AS sku, p.id AS product_id
)
ORDER BY order_id, sku
"""

SINGLE_HOP_ROWS = (
    {"customer_id": "cust_ada", "order_id": "ord_1001", "status": "open"},
    {"customer_id": "cust_ada", "order_id": "ord_1002", "status": "shipped"},
    {"customer_id": "cust_bob", "order_id": "ord_2001", "status": "open"},
)
MULTI_HOP_ROWS = (
    {
        "customer_id": "cust_ada",
        "order_id": "ord_1001",
        "sku": "SKU_G",
        "quantity": "1",
        "product_id": "prod_gadget",
        "product_name": "Gadget",
    },
    {
        "customer_id": "cust_ada",
        "order_id": "ord_1001",
        "sku": "SKU_W",
        "quantity": "2",
        "product_id": "prod_widget",
        "product_name": "Widget",
    },
    {
        "customer_id": "cust_ada",
        "order_id": "ord_1002",
        "sku": "SKU_W",
        "quantity": "4",
        "product_id": "prod_widget",
        "product_name": "Widget",
    },
    {
        "customer_id": "cust_bob",
        "order_id": "ord_2001",
        "sku": "SKU_S",
        "quantity": "3",
        "product_id": "prod_sprocket",
        "product_name": "Sprocket",
    },
)
COMPOSITE_ROWS = (
    {"order_id": "ord_1001", "sku": "SKU_W", "product_id": "prod_widget"},
    {"order_id": "ord_1002", "sku": "SKU_W", "product_id": "prod_widget"},
)


def graph_table_sql(template: str, graph_target: str) -> str:
    """Interpolate a quoted graph name into a GRAPH_TABLE query."""

    return template.format(graph=quote_resource(graph_target))


def single_hop_sql(graph_target: str) -> str:
    """Customer -PLACED-> Order sanity query."""

    return graph_table_sql(_SINGLE_HOP, graph_target)


def multi_hop_sql(graph_target: str) -> str:
    """Customer → Order → OrderItem → Product multi-hop query."""

    return graph_table_sql(_MULTI_HOP, graph_target)


def composite_item_sql(graph_target: str) -> str:
    """OrderItem composite key (orderId, sku) via OF."""

    return graph_table_sql(_COMPOSITE_ITEMS, graph_target)
