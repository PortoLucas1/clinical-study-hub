-- @param study_id STRING = ONC-101
SELECT
  study_id, nct_id, title, phase, indication, therapeutic_area, sponsor,
  array_join(arms, ' vs ') AS arms_label,
  planned_enrollment, planned_sites,
  CAST(study_start_date AS STRING) AS study_start_date,
  CAST(data_cutoff_date AS STRING) AS data_cutoff_date,
  submission_id,
  enrolled, randomized, active_sites, countries, pct_enrollment_target,
  ongoing, completed, discontinued, discontinued_due_to_ae, discontinuation_rate_pct,
  total_aes, subjects_with_ae, total_saes, subjects_with_sae, grade3plus_aes, fatal_aes, sae_subject_rate_pct,
  dq_issues, dq_high_issues,
  subjects_received, subjects_clean, subjects_quarantined, pct_subjects_clean, records_received, records_quarantined
FROM clinical_demo.study_onboarding.gold_study_overview
WHERE study_id = :study_id
