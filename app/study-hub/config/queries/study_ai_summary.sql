-- @param study_id STRING = ONC-101
SELECT
  study_id,
  submission_id,
  headline,
  summary,
  findings_json,
  recommended_actions_json,
  model,
  CAST(generated_at AS STRING) AS generated_at
FROM clinical_demo.study_onboarding.gold_study_ai_summary
WHERE study_id = :study_id
