SELECT
  study_id,
  status,
  breaches
FROM clinical_demo.study_onboarding.dq_study_status
ORDER BY study_id
