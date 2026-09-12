SELECT
  projected.key_0,
  COUNT(*) AS violation_count,
  COUNT(*) OVER() AS total_violations
FROM (
  SELECT
    order_id AS key_0
  FROM `my-project.raw.orders`
) AS projected
WHERE projected.key_0 IS NOT NULL
GROUP BY
  projected.key_0
HAVING COUNT(*) > 1
ORDER BY
  violation_count DESC,
  projected.key_0
LIMIT 20
