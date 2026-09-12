SELECT
  edge.orderId,
  edge.sku,
  COUNT(*) AS violation_count,
  COUNT(*) OVER() AS total_violations
FROM (
  SELECT
    order_id AS orderId,
    sku AS sku
  FROM `my-project.raw.order_items`
) AS edge
LEFT JOIN (
  SELECT
    order_id AS orderId,
    sku AS sku
  FROM `my-project.raw.order_items`
) AS node
ON edge.orderId = node.orderId AND edge.sku = node.sku
WHERE node.orderId IS NULL AND node.sku IS NULL
GROUP BY
  edge.orderId,
  edge.sku
ORDER BY
  violation_count DESC,
  edge.orderId,
  edge.sku
LIMIT 20
