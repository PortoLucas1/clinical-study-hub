-- Quarantine-first data quality checks. Every row must report failures = 0.
-- Replace clinical_demo.study_onboarding with your catalog and schema (00_install.py does this for app queries).
WITH status AS (
  SELECT study_id, usubjid, is_clean FROM clinical_demo.study_onboarding.silver_subject_status
),
leaks AS (
  SELECT 'silver_dm' AS tbl, study_id, usubjid FROM clinical_demo.study_onboarding.silver_dm
  UNION ALL SELECT 'silver_ae', study_id, usubjid FROM clinical_demo.study_onboarding.silver_ae
  UNION ALL SELECT 'silver_vs', study_id, usubjid FROM clinical_demo.study_onboarding.silver_vs
  UNION ALL SELECT 'silver_lb', study_id, usubjid FROM clinical_demo.study_onboarding.silver_lb
  UNION ALL SELECT 'silver_ex', study_id, usubjid FROM clinical_demo.study_onboarding.silver_ex
  UNION ALL SELECT 'silver_ds', study_id, usubjid FROM clinical_demo.study_onboarding.silver_ds
  UNION ALL SELECT 'silver_sv', study_id, usubjid FROM clinical_demo.study_onboarding.silver_sv
  UNION ALL SELECT 'gold_patient_profile', study_id, usubjid FROM clinical_demo.study_onboarding.gold_patient_profile
),
quarantine AS (
  SELECT study_id, usubjid FROM clinical_demo.study_onboarding.silver_dm_quarantine
  UNION ALL SELECT study_id, usubjid FROM clinical_demo.study_onboarding.silver_ae_quarantine
  UNION ALL SELECT study_id, usubjid FROM clinical_demo.study_onboarding.silver_vs_quarantine
  UNION ALL SELECT study_id, usubjid FROM clinical_demo.study_onboarding.silver_lb_quarantine
  UNION ALL SELECT study_id, usubjid FROM clinical_demo.study_onboarding.silver_ex_quarantine
  UNION ALL SELECT study_id, usubjid FROM clinical_demo.study_onboarding.silver_ds_quarantine
  UNION ALL SELECT study_id, usubjid FROM clinical_demo.study_onboarding.silver_sv_quarantine
)
SELECT 'every staged row lands in clean or quarantine (dq_reconciliation)' AS check_name,
       count_if(NOT balanced) AS failures
FROM clinical_demo.study_onboarding.dq_reconciliation
UNION ALL
SELECT 'no quarantined or unknown subject in clean Silver or Gold tables',
       count(*)
FROM leaks l LEFT JOIN status s USING (study_id, usubjid)
WHERE s.is_clean IS NULL OR NOT s.is_clean
UNION ALL
SELECT 'clean subjects have no quarantined records',
       count(*)
FROM quarantine q JOIN status s USING (study_id, usubjid)
WHERE s.is_clean
UNION ALL
SELECT 'quarantined subjects have quarantined records',
       count(*)
FROM status s LEFT ANTI JOIN quarantine q USING (study_id, usubjid)
WHERE NOT s.is_clean
UNION ALL
SELECT 'subjects_received = subjects_clean + subjects_quarantined (gold_study_overview)',
       count_if(subjects_received <> subjects_clean + subjects_quarantined)
FROM clinical_demo.study_onboarding.gold_study_overview
UNION ALL
SELECT 'gold_study_overview.enrolled counts clean subjects only',
       count_if(enrolled > subjects_clean)
FROM clinical_demo.study_onboarding.gold_study_overview
UNION ALL
SELECT 'accepted (waived) issues of the current submission are not quarantined',
       count(*)
FROM clinical_demo.study_onboarding.dq_waivers w
JOIN clinical_demo.study_onboarding.study_registry r
  ON r.study_id = w.study_id AND r.latest_submission_id = w.submission_id
JOIN clinical_demo.study_onboarding.gold_dq_issues i
  ON i.study_id = w.study_id AND upper(i.domain) = upper(w.domain) AND i.rule_id = w.rule_id
 AND i.usubjid = w.usubjid AND i.action = 'quarantine'
UNION ALL
SELECT 'every threshold status row has a known status',
       count_if(status NOT IN ('ok', 'warn', 'critical'))
FROM clinical_demo.study_onboarding.dq_threshold_status
ORDER BY check_name;
