-- @param study_id STRING = ONC-101
SELECT
  system_organ_class,
  arm,
  SUM(subjects) AS subjects,
  SUM(events) AS events,
  SUM(serious_events) AS serious_events
FROM clinical_demo.study_onboarding.gold_ae_summary
WHERE study_id = :study_id
GROUP BY system_organ_class, arm
ORDER BY system_organ_class, arm
