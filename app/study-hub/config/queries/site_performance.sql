-- @param study_id STRING = ONC-101
SELECT
  site_id,
  country,
  enrolled,
  discontinued,
  discontinuation_rate_pct,
  saes,
  visits_completed,
  out_of_window_visits,
  pct_visits_out_of_window,
  dq_issues
FROM clinical_demo.study_onboarding.gold_site_performance
WHERE study_id = :study_id
ORDER BY site_id
