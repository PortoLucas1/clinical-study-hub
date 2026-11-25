-- @param study_id STRING = ONC-101
SELECT
  lab_test,
  arm,
  ROUND(SUM(high_count + low_count) * 100.0 / NULLIF(SUM(results), 0), 1) AS pct_abnormal,
  SUM(results) AS results
FROM clinical_demo.study_onboarding.gold_lab_abnormalities
WHERE study_id = :study_id AND visitnum >= 2
GROUP BY lab_test, arm
ORDER BY lab_test, arm
