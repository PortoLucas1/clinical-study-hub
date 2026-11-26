SELECT
  o.study_id,
  o.title,
  o.phase,
  o.indication,
  o.therapeutic_area,
  o.sponsor,
  o.planned_enrollment,
  o.enrolled,
  o.pct_enrollment_target,
  o.active_sites,
  o.countries,
  o.discontinuation_rate_pct,
  o.sae_subject_rate_pct,
  o.dq_issues,
  o.dq_high_issues,
  CAST(o.data_cutoff_date AS STRING) AS data_cutoff_date,
  a.headline,
  CAST(a.generated_at AS STRING) AS insights_generated_at,
  o.subjects_received,
  o.subjects_clean,
  o.subjects_quarantined,
  o.pct_subjects_clean,
  o.records_quarantined
FROM clinical_demo.study_onboarding.gold_study_overview o
LEFT JOIN clinical_demo.study_onboarding.gold_study_ai_summary a USING (study_id)
ORDER BY o.study_id
