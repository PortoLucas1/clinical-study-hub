-- @param study_id STRING = ONC-101
SELECT
  date_format(enroll_month, 'yyyy-MM') AS month,
  arm,
  new_subjects,
  cumulative_subjects
FROM clinical_demo.study_onboarding.gold_enrollment_by_month
WHERE study_id = :study_id AND enroll_month IS NOT NULL
ORDER BY month, arm
