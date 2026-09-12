SELECT
  edge.id,
  COUNT(*) AS violation_count,
  COUNT(*) OVER() AS total_violations
FROM (
  SELECT
    order_id AS id
  FROM `my-project.raw.orders`
) AS edge
LEFT JOIN (
  SELECT
    order_id AS id
  FROM `my-project.raw.orders`
) AS node
ON edge.id = node.id
WHERE node.id IS NULL
GROUP BY
  edge.id
ORDER BY
  violation_count DESC,
  edge.id
LIMIT 20
