-- @param study_id STRING = ONC-101
-- @param lab_test STRING = ALT
SELECT
  visit,
  visitnum,
  arm,
  mean_value,
  pct_abnormal,
  unit,
  ref_low,
  ref_high
FROM clinical_demo.study_onboarding.gold_lab_abnormalities
WHERE study_id = :study_id AND lab_test = :lab_test
ORDER BY visitnum, arm
