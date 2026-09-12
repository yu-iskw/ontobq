SELECT
  projected.id,
  COUNT(*) AS violation_count,
  COUNT(*) OVER() AS total_violations
FROM (
  SELECT
    customer_id AS id
  FROM `my-project.raw.customers`
) AS projected
WHERE projected.id IS NULL
GROUP BY
  projected.id
ORDER BY
  violation_count DESC,
  projected.id
LIMIT 20
