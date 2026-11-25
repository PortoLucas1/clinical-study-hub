-- @param study_id STRING = ONC-101
SELECT
  COALESCE(discontinuation_reason, disposition_status) AS category,
  disposition_status,
  COUNT(*) AS subjects
FROM clinical_demo.study_onboarding.gold_patient_profile
WHERE study_id = :study_id
GROUP BY ALL
ORDER BY subjects DESC
