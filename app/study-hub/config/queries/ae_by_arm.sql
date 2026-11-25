-- @param study_id STRING = ONC-101
SELECT
  arm,
  subjects_in_arm,
  subjects_with_ae,
  pct_with_ae,
  subjects_with_sae,
  pct_with_sae,
  subjects_grade3plus,
  pct_grade3plus,
  total_events,
  discontinued_due_to_ae
FROM clinical_demo.study_onboarding.gold_ae_by_arm
WHERE study_id = :study_id
ORDER BY arm
