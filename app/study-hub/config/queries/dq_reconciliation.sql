-- @param study_id STRING = ONC-101
SELECT
  domain,
  staged_rows,
  bronze_rows,
  clean_rows,
  quarantine_rows,
  balanced
FROM clinical_demo.study_onboarding.dq_reconciliation
WHERE study_id = :study_id
ORDER BY domain
