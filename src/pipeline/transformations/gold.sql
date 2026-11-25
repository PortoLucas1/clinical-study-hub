-- Gold: study insight marts consumed by the Study Hub app and the Genie agent.
-- Every table keeps study_id (plus arm / site / visit where relevant) so the app and
-- Genie can slice any study without re-aggregating.

CREATE OR REFRESH MATERIALIZED VIEW gold_patient_profile
COMMENT "One row per subject: demographics, disposition, exposure, safety and visit summary"
TBLPROPERTIES ("quality" = "gold")
AS
WITH ae AS (
  SELECT study_id, usubjid,
         count(*) AS ae_count,
         count_if(aeser = 'Y') AS sae_count,
         max(aetoxgr) AS max_ae_grade,
         count_if(aerel = 'Y') AS related_ae_count
  FROM silver_ae GROUP BY study_id, usubjid
),
lb AS (
  SELECT study_id, usubjid, count_if(lbnrind IN ('HIGH', 'LOW')) AS abnormal_lab_count
  FROM silver_lb GROUP BY study_id, usubjid
),
sv AS (
  SELECT study_id, usubjid, count(*) AS visits_completed, max(svstdtc) AS last_visit_date,
         count_if(abs(days_from_planned) > 7) AS out_of_window_visits
  FROM silver_sv GROUP BY study_id, usubjid
)
SELECT
  dm.study_id, dm.usubjid, dm.siteid AS site_id, dm.country, dm.arm, dm.sex, dm.age, dm.race, dm.ethnic, dm.bmi,
  dm.rficdtc AS consent_date, dm.randdt AS randomization_date,
  ds.dsdecod AS disposition_status, ds.dsterm AS discontinuation_reason, ds.dsstdtc AS disposition_date,
  ex.extrt AS treatment, ex.exdose AS dose, ex.exdosu AS dose_unit,
  ex.exstdtc AS first_dose_date, ex.exendtc AS last_dose_date,
  datediff(coalesce(ex.exendtc, st.data_cutoff_date), ex.exstdtc) AS days_on_treatment,
  coalesce(ae.ae_count, 0) AS ae_count,
  coalesce(ae.sae_count, 0) AS sae_count,
  coalesce(ae.related_ae_count, 0) AS related_ae_count,
  ae.max_ae_grade,
  coalesce(lb.abnormal_lab_count, 0) AS abnormal_lab_count,
  coalesce(sv.visits_completed, 0) AS visits_completed,
  sv.last_visit_date,
  coalesce(sv.out_of_window_visits, 0) AS out_of_window_visits
FROM silver_dm dm
LEFT JOIN silver_study st ON st.study_id = dm.study_id
LEFT JOIN silver_ds ds ON ds.study_id = dm.study_id AND ds.usubjid = dm.usubjid
LEFT JOIN silver_ex ex ON ex.study_id = dm.study_id AND ex.usubjid = dm.usubjid
LEFT JOIN ae ON ae.study_id = dm.study_id AND ae.usubjid = dm.usubjid
LEFT JOIN lb ON lb.study_id = dm.study_id AND lb.usubjid = dm.usubjid
LEFT JOIN sv ON sv.study_id = dm.study_id AND sv.usubjid = dm.usubjid;

CREATE OR REFRESH MATERIALIZED VIEW gold_dq_issues
COMMENT "Data quality: one row per detected data issue (rule, subject, site, detail)"
TBLPROPERTIES ("quality" = "gold")
AS
SELECT study_id, 'DM' AS domain, 'DM01' AS rule_id, 'Age outside protocol range (18-100)' AS rule_description,
       'High' AS severity, usubjid, siteid AS site_id, concat('AGE=', coalesce(cast(age AS STRING), 'missing')) AS detail
FROM silver_dm WHERE age IS NULL OR age NOT BETWEEN 18 AND 100
UNION ALL
SELECT study_id, 'DM', 'DM02', 'Informed consent date missing', 'High', usubjid, siteid, 'RFICDTC is null'
FROM silver_dm WHERE rficdtc IS NULL
UNION ALL
SELECT ae.study_id, 'AE', 'AE01', 'AE end date before onset date', 'Medium', ae.usubjid, dm.siteid,
       concat(ae.aeterm, ': onset ', ae.aestdtc, ', end ', ae.aeendtc)
FROM silver_ae ae LEFT JOIN silver_dm dm USING (study_id, usubjid)
WHERE ae.aeendtc < ae.aestdtc
UNION ALL
SELECT ae.study_id, 'AE', 'AE02', 'AE onset before randomization', 'Low', ae.usubjid, dm.siteid,
       concat(ae.aeterm, ': onset ', ae.aestdtc, ', randomized ', dm.randdt)
FROM silver_ae ae JOIN silver_dm dm USING (study_id, usubjid)
WHERE ae.aestdtc < dm.randdt
UNION ALL
SELECT lb.study_id, 'LB', 'LB01', 'Lab result not numeric or missing', 'Medium', lb.usubjid, dm.siteid,
       concat(lb.lbtestcd, ' at ', lb.visit, ': "', coalesce(lb.lborres, ''), '"')
FROM silver_lb lb LEFT JOIN silver_dm dm USING (study_id, usubjid)
WHERE lb.lbstresn IS NULL
UNION ALL
SELECT vs.study_id, 'VS', 'VS01', 'Vital sign physiologically implausible', 'High', vs.usubjid, dm.siteid,
       concat(vs.vstestcd, '=', vs.vsorres, ' ', vs.vsstresu, ' at ', vs.visit)
FROM silver_vs vs LEFT JOIN silver_dm dm USING (study_id, usubjid)
WHERE NOT (CASE vs.vstestcd
             WHEN 'SYSBP' THEN vs.vsstresn BETWEEN 60 AND 250
             WHEN 'DIABP' THEN vs.vsstresn BETWEEN 30 AND 150
             WHEN 'HR' THEN vs.vsstresn BETWEEN 30 AND 220
             WHEN 'TEMP' THEN vs.vsstresn BETWEEN 33 AND 42
             WHEN 'WEIGHT' THEN vs.vsstresn BETWEEN 25 AND 300
             ELSE TRUE END)
UNION ALL
SELECT sv.study_id, 'SV', 'SV01', 'Visit outside protocol window (+/- 7 days)', 'Low', sv.usubjid, dm.siteid,
       concat(sv.visit, ': ', sv.days_from_planned, ' days from planned')
FROM silver_sv sv LEFT JOIN silver_dm dm USING (study_id, usubjid)
WHERE abs(sv.days_from_planned) > 7;

CREATE OR REFRESH MATERIALIZED VIEW gold_dq_summary
COMMENT "Data quality summary: issue counts by study, domain and rule"
TBLPROPERTIES ("quality" = "gold")
AS
SELECT study_id, domain, rule_id, rule_description, severity,
       count(*) AS issue_count,
       count(DISTINCT usubjid) AS subjects_affected,
       count(DISTINCT site_id) AS sites_affected
FROM gold_dq_issues
GROUP BY study_id, domain, rule_id, rule_description, severity;

CREATE OR REFRESH MATERIALIZED VIEW gold_study_overview
COMMENT "One row per study: protocol info, enrollment vs plan, disposition, safety and data quality KPIs"
TBLPROPERTIES ("quality" = "gold")
AS
WITH dm AS (
  SELECT study_id, count(*) AS enrolled, count(randdt) AS randomized,
         count(DISTINCT siteid) AS active_sites, count(DISTINCT country) AS countries,
         min(rficdtc) AS first_subject_consented, max(rficdtc) AS last_subject_consented
  FROM silver_dm GROUP BY study_id
),
ds AS (
  SELECT study_id, count_if(dsdecod = 'ONGOING') AS ongoing, count_if(dsdecod = 'COMPLETED') AS completed,
         count_if(dsdecod = 'DISCONTINUED') AS discontinued,
         count_if(dsdecod = 'DISCONTINUED' AND dsterm = 'ADVERSE EVENT') AS discontinued_due_to_ae
  FROM silver_ds GROUP BY study_id
),
ae AS (
  SELECT study_id, count(*) AS total_aes, count(DISTINCT usubjid) AS subjects_with_ae,
         count_if(aeser = 'Y') AS total_saes, count(DISTINCT CASE WHEN aeser = 'Y' THEN usubjid END) AS subjects_with_sae,
         count_if(aetoxgr >= 3) AS grade3plus_aes, count_if(aeout = 'FATAL') AS fatal_aes
  FROM silver_ae GROUP BY study_id
),
dq AS (
  SELECT study_id, count(*) AS dq_issues, count_if(severity = 'High') AS dq_high_issues
  FROM gold_dq_issues GROUP BY study_id
)
SELECT
  s.study_id, s.nct_id, s.title, s.phase, s.indication, s.therapeutic_area, s.sponsor,
  s.arms, s.planned_enrollment, s.planned_sites, s.study_start_date, s.data_cutoff_date, s.submission_id,
  dm.enrolled, dm.randomized, dm.active_sites, dm.countries,
  round(100.0 * dm.enrolled / nullif(s.planned_enrollment, 0), 1) AS pct_enrollment_target,
  dm.first_subject_consented, dm.last_subject_consented,
  ds.ongoing, ds.completed, ds.discontinued, ds.discontinued_due_to_ae,
  round(100.0 * ds.discontinued / nullif(dm.enrolled, 0), 1) AS discontinuation_rate_pct,
  ae.total_aes, ae.subjects_with_ae, ae.total_saes, ae.subjects_with_sae, ae.grade3plus_aes, ae.fatal_aes,
  round(100.0 * ae.subjects_with_sae / nullif(dm.enrolled, 0), 1) AS sae_subject_rate_pct,
  coalesce(dq.dq_issues, 0) AS dq_issues, coalesce(dq.dq_high_issues, 0) AS dq_high_issues
FROM silver_study s
LEFT JOIN dm USING (study_id)
LEFT JOIN ds USING (study_id)
LEFT JOIN ae USING (study_id)
LEFT JOIN dq USING (study_id);

CREATE OR REFRESH MATERIALIZED VIEW gold_enrollment_by_month
COMMENT "Monthly enrollment (by consent date) per study and arm, with cumulative totals"
TBLPROPERTIES ("quality" = "gold")
AS
WITH m AS (
  SELECT study_id, arm, date_trunc('MONTH', coalesce(rficdtc, randdt))::DATE AS enroll_month, count(*) AS new_subjects
  FROM silver_dm GROUP BY ALL
)
SELECT study_id, arm, enroll_month, new_subjects,
       sum(new_subjects) OVER (PARTITION BY study_id, arm ORDER BY enroll_month) AS cumulative_subjects
FROM m;

CREATE OR REFRESH MATERIALIZED VIEW gold_site_performance
COMMENT "Clinical operations view per site: enrollment, discontinuations, SAEs, visit compliance and data quality"
TBLPROPERTIES ("quality" = "gold")
AS
WITH dq AS (SELECT study_id, site_id, count(*) AS dq_issues FROM gold_dq_issues GROUP BY ALL)
SELECT p.study_id, p.site_id, p.country,
       count(*) AS enrolled,
       count_if(p.disposition_status = 'DISCONTINUED') AS discontinued,
       round(100.0 * count_if(p.disposition_status = 'DISCONTINUED') / count(*), 1) AS discontinuation_rate_pct,
       sum(p.sae_count) AS saes,
       sum(p.visits_completed) AS visits_completed,
       sum(p.out_of_window_visits) AS out_of_window_visits,
       round(100.0 * sum(p.out_of_window_visits) / nullif(sum(p.visits_completed), 0), 1) AS pct_visits_out_of_window,
       coalesce(max(dq.dq_issues), 0) AS dq_issues
FROM gold_patient_profile p
LEFT JOIN dq ON dq.study_id = p.study_id AND dq.site_id = p.site_id
GROUP BY p.study_id, p.site_id, p.country;

CREATE OR REFRESH MATERIALIZED VIEW gold_ae_summary
COMMENT "Adverse events by study, arm, system organ class and preferred term"
TBLPROPERTIES ("quality" = "gold")
AS
SELECT ae.study_id, dm.arm, ae.aesoc AS system_organ_class, ae.aedecod AS preferred_term,
       count(*) AS events,
       count(DISTINCT ae.usubjid) AS subjects,
       count_if(ae.aeser = 'Y') AS serious_events,
       count_if(ae.aetoxgr >= 3) AS grade3plus_events,
       count_if(ae.aerel = 'Y') AS related_events,
       max(ae.aetoxgr) AS max_grade
FROM silver_ae ae JOIN silver_dm dm USING (study_id, usubjid)
GROUP BY ae.study_id, dm.arm, ae.aesoc, ae.aedecod;

CREATE OR REFRESH MATERIALIZED VIEW gold_ae_by_arm
COMMENT "Safety overview per treatment arm: share of subjects with any AE, SAE, grade 3+ AE and AE-related discontinuation"
TBLPROPERTIES ("quality" = "gold")
AS
SELECT study_id, arm,
       count(*) AS subjects_in_arm,
       count_if(ae_count > 0) AS subjects_with_ae,
       round(100.0 * count_if(ae_count > 0) / count(*), 1) AS pct_with_ae,
       count_if(sae_count > 0) AS subjects_with_sae,
       round(100.0 * count_if(sae_count > 0) / count(*), 1) AS pct_with_sae,
       count_if(max_ae_grade >= 3) AS subjects_grade3plus,
       round(100.0 * count_if(max_ae_grade >= 3) / count(*), 1) AS pct_grade3plus,
       sum(ae_count) AS total_events,
       count_if(discontinuation_reason = 'ADVERSE EVENT') AS discontinued_due_to_ae
FROM gold_patient_profile
GROUP BY study_id, arm;

CREATE OR REFRESH MATERIALIZED VIEW gold_lab_abnormalities
COMMENT "Central lab results by study, arm, test and visit: abnormal (out of reference range) rates and mean values"
TBLPROPERTIES ("quality" = "gold")
AS
SELECT lb.study_id, dm.arm, lb.lbtestcd AS lab_test, lb.visit, lb.visitnum, any_value(lb.lbstresu) AS unit,
       any_value(lb.lbornrlo) AS ref_low, any_value(lb.lbornrhi) AS ref_high,
       count(lb.lbstresn) AS results,
       count_if(lb.lbnrind = 'HIGH') AS high_count,
       count_if(lb.lbnrind = 'LOW') AS low_count,
       round(100.0 * count_if(lb.lbnrind IN ('HIGH', 'LOW')) / nullif(count(lb.lbstresn), 0), 1) AS pct_abnormal,
       round(avg(lb.lbstresn), 2) AS mean_value
FROM silver_lb lb JOIN silver_dm dm USING (study_id, usubjid)
GROUP BY lb.study_id, dm.arm, lb.lbtestcd, lb.visit, lb.visitnum;

CREATE OR REFRESH MATERIALIZED VIEW gold_vitals_trends
COMMENT "Mean vital signs by study, arm, test and visit (implausible values excluded)"
TBLPROPERTIES ("quality" = "gold")
AS
SELECT vs.study_id, dm.arm, vs.vstestcd AS vital_test, vs.visit, vs.visitnum, any_value(vs.vsstresu) AS unit,
       count(*) AS measurements,
       round(avg(vs.vsstresn), 1) AS mean_value
FROM silver_vs vs JOIN silver_dm dm USING (study_id, usubjid)
WHERE vs.vsstresn IS NOT NULL
  AND (CASE vs.vstestcd
         WHEN 'SYSBP' THEN vs.vsstresn BETWEEN 60 AND 250
         WHEN 'DIABP' THEN vs.vsstresn BETWEEN 30 AND 150
         WHEN 'HR' THEN vs.vsstresn BETWEEN 30 AND 220
         WHEN 'TEMP' THEN vs.vsstresn BETWEEN 33 AND 42
         WHEN 'WEIGHT' THEN vs.vsstresn BETWEEN 25 AND 300
         ELSE TRUE END)
GROUP BY vs.study_id, dm.arm, vs.vstestcd, vs.visit, vs.visitnum;
