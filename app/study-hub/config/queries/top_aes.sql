-- @param study_id STRING = ONC-101
SELECT
  preferred_term,
  system_organ_class,
  SUM(events) AS events,
  SUM(subjects) AS subjects,
  SUM(serious_events) AS serious_events,
  SUM(grade3plus_events) AS grade3plus_events,
  MAX(max_grade) AS max_grade
FROM clinical_demo.study_onboarding.gold_ae_summary
WHERE study_id = :study_id
GROUP BY preferred_term, system_organ_class
ORDER BY events DESC
LIMIT 12
