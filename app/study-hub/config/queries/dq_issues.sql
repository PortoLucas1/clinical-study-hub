-- @param study_id STRING = ONC-101
SELECT
  rule_id,
  severity,
  domain,
  usubjid,
  site_id,
  detail
FROM clinical_demo.study_onboarding.gold_dq_issues
WHERE study_id = :study_id
ORDER BY CASE severity WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, rule_id, usubjid
LIMIT 500
