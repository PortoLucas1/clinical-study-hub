-- @param submission_id STRING = SUB-00000000000000-DEMO
SELECT
  attempt,
  actor,
  scenario,
  accuracy_pct,
  threshold_pct,
  outcome,
  wrong_columns,
  feedback,
  CAST(recorded_at AS STRING) AS recorded_at
FROM clinical_demo.study_onboarding.ai_modelling_runs
WHERE submission_id = :submission_id
ORDER BY recorded_at, attempt
