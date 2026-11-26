-- @param study_id STRING = ONC-101
SELECT
  domain,
  rule_id,
  rule_description,
  severity,
  action,
  usubjid,
  site_id,
  detail
FROM clinical_demo.study_onboarding.gold_dq_issues
WHERE study_id = :study_id
ORDER BY CASE action WHEN 'quarantine' THEN 0 ELSE 1 END,
  CASE severity WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, domain, rule_id, usubjid
LIMIT 1000
