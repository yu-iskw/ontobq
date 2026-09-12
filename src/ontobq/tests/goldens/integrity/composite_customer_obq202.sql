SELECT
  projected.tenantId,
  projected.id,
  COUNT(*) AS violation_count,
  COUNT(*) OVER() AS total_violations
FROM (
  SELECT
    tenant_id AS tenantId,
    customer_id AS id
  FROM `my-project.raw.customers`
) AS projected
WHERE projected.tenantId IS NOT NULL AND projected.id IS NOT NULL
GROUP BY
  projected.tenantId,
  projected.id
HAVING COUNT(*) > 1
ORDER BY
  violation_count DESC,
  projected.tenantId,
  projected.id
LIMIT 20
