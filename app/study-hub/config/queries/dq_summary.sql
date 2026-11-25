-- @param study_id STRING = ONC-101
SELECT
  rule_id,
  domain,
  rule_description,
  severity,
  issue_count,
  subjects_affected,
  sites_affected
FROM clinical_demo.study_onboarding.gold_dq_summary
WHERE study_id = :study_id
ORDER BY CASE severity WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, issue_count DESC
