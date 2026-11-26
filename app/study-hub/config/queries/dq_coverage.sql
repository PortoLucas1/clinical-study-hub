-- @param study_id STRING = ONC-101
SELECT
  subjects_received,
  subjects_clean,
  subjects_quarantined,
  pct_subjects_clean,
  records_received,
  records_quarantined
FROM clinical_demo.study_onboarding.dq_study_coverage
WHERE study_id = :study_id
