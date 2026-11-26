-- @param study_id STRING = ONC-101
SELECT
  usubjid,
  site_id,
  country,
  records_quarantined,
  array_join(failed_rules, ', ') AS failed_rules,
  dm_quarantined,
  ae_quarantined,
  vs_quarantined,
  lb_quarantined,
  ex_quarantined,
  ds_quarantined,
  sv_quarantined
FROM clinical_demo.study_onboarding.silver_subject_status
WHERE study_id = :study_id AND NOT is_clean
ORDER BY records_quarantined DESC, usubjid
