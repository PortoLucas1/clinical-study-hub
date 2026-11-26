-- @param study_id STRING = ONC-101
SELECT
  metric,
  value,
  warn,
  critical,
  status,
  description
FROM clinical_demo.study_onboarding.dq_threshold_status
WHERE study_id = :study_id
ORDER BY CASE status WHEN 'critical' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END, metric
