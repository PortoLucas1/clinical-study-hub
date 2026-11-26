-- @param submission_id STRING = SUB-00000000000000-DEMO
SELECT
  domain,
  source_file,
  row_count,
  status,
  missing_columns
FROM clinical_demo.study_onboarding.submission_files
WHERE submission_id = :submission_id
QUALIFY row_number() OVER (PARTITION BY source_file ORDER BY staged_at DESC) = 1
ORDER BY CASE WHEN status = 'staged' AND missing_columns IS NULL THEN 1 ELSE 0 END, domain, source_file
