SELECT
  projected.createdAt,
  COUNT(*) AS violation_count,
  COUNT(*) OVER() AS total_violations
FROM (
  SELECT
    TIMESTAMP(created_at) AS createdAt
  FROM `my-project.raw.orders`
) AS projected
WHERE projected.createdAt IS NULL
GROUP BY
  projected.createdAt
ORDER BY
  violation_count DESC,
  projected.createdAt
LIMIT 20
