# Databricks notebook source
# MAGIC %md
# MAGIC # 05 - Data quality threshold check
# MAGIC
# MAGIC Compares each study's data quality with the thresholds in `dq_thresholds` and records the result. It never
# MAGIC fails the job and never blocks publishing: quarantine already keeps unclean data out of Gold, so a breach is a
# MAGIC signal for the data management team, not a reason to stop. The team is notified by the SQL alert on
# MAGIC `dq_study_status` and sees the details in the data quality dashboard and the Study Hub.
# MAGIC
# MAGIC | Metric | Meaning | Default warn | Default critical |
# MAGIC |---|---|---|---|
# MAGIC | `pct_subjects_quarantined` | Share of received subjects that are quarantined | 15 | 25 |
# MAGIC | `top_rule_share_pct` | Share of quarantined subjects hit by the single most common rule (a high value points to a mapping or schema problem, not scattered dirty data) | 50 | 75 |
# MAGIC | `reconciliation_failures` | Domains where staged = bronze = clean + quarantine does not hold | 1 | 1 |
# MAGIC
# MAGIC The defaults are calibrated to the seeded defects in the synthetic demo data (21 to 29 percent of subjects are
# MAGIC quarantined). A production setup would use much tighter values, for example 2 and 5 percent. Edit the table to
# MAGIC change them; a row with a `study_id` overrides the default for that study.
# MAGIC
# MAGIC Outputs: `dq_thresholds` (editable), `dq_threshold_status` and `dq_study_status` (views), `dq_run_history`
# MAGIC (one snapshot per study per run, for trends).

# COMMAND ----------

import uuid

for name in ["catalog", "schema", "run_id"]:
    dbutils.widgets.text(name, "")

catalog = dbutils.widgets.get("catalog").strip() or "clinical_demo"
schema = dbutils.widgets.get("schema").strip() or "study_onboarding"
run_id = dbutils.widgets.get("run_id").strip() or f"manual-{uuid.uuid4().hex[:8]}"
fq = f"{catalog}.{schema}"

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {fq}.dq_thresholds (
  metric STRING, study_id STRING, warn DOUBLE, critical DOUBLE, description STRING
) COMMENT 'Editable data quality thresholds. study_id NULL is the default for every study; a study row overrides it.'
""")
DEFAULTS = [
    ("pct_subjects_quarantined", 15.0, 25.0, "Percent of received subjects that are quarantined"),
    ("top_rule_share_pct", 50.0, 75.0, "Percent of quarantined subjects hit by the single most common rule"),
    ("reconciliation_failures", 1.0, 1.0, "Domains where staged = bronze = clean + quarantine does not balance"),
]
for metric, warn, critical, description in DEFAULTS:
    spark.sql(
        f"""MERGE INTO {fq}.dq_thresholds t
            USING (SELECT '{metric}' AS metric, CAST(NULL AS STRING) AS study_id, {warn} AS warn,
                          {critical} AS critical, '{description}' AS description) s
            ON t.metric = s.metric AND t.study_id <=> s.study_id
            WHEN NOT MATCHED THEN INSERT *"""
    )

spark.sql(f"""
CREATE OR REPLACE VIEW {fq}.dq_threshold_status
COMMENT 'Per study and metric: current value, thresholds (study override or default) and status ok, warn or critical'
AS
WITH metrics AS (
  SELECT study_id, 'pct_subjects_quarantined' AS metric,
         round(100.0 * subjects_quarantined / nullif(subjects_received, 0), 1) AS value
  FROM {fq}.dq_study_coverage
  UNION ALL
  SELECT c.study_id, 'top_rule_share_pct' AS metric,
         round(100.0 * coalesce(max(g.subjects_affected), 0) / nullif(max(c.subjects_quarantined), 0), 1) AS value
  FROM {fq}.dq_study_coverage c
  LEFT JOIN {fq}.gold_dq_summary g ON g.study_id = c.study_id AND g.action = 'quarantine'
  GROUP BY c.study_id
  UNION ALL
  SELECT c.study_id, 'reconciliation_failures' AS metric, CAST(count_if(NOT coalesce(r.balanced, TRUE)) AS DOUBLE) AS value
  FROM {fq}.dq_study_coverage c
  LEFT JOIN {fq}.dq_reconciliation r ON r.study_id = c.study_id
  GROUP BY c.study_id
)
SELECT m.study_id, m.metric, m.value,
       coalesce(o.warn, d.warn) AS warn, coalesce(o.critical, d.critical) AS critical,
       CASE WHEN m.value IS NULL THEN 'ok'
            WHEN m.value >= coalesce(o.critical, d.critical) THEN 'critical'
            WHEN m.value >= coalesce(o.warn, d.warn) THEN 'warn'
            ELSE 'ok' END AS status,
       coalesce(o.description, d.description) AS description,
       o.study_id IS NOT NULL AS study_override
FROM metrics m
LEFT JOIN {fq}.dq_thresholds d ON d.metric = m.metric AND d.study_id IS NULL
LEFT JOIN {fq}.dq_thresholds o ON o.metric = m.metric AND o.study_id = m.study_id
""")

spark.sql(f"""
CREATE OR REPLACE VIEW {fq}.dq_study_status
COMMENT 'Worst data quality threshold status per study (critical, warn or ok) with the metrics that breached. Source of the SQL alert.'
AS
SELECT study_id,
       CASE max(CASE status WHEN 'critical' THEN 2 WHEN 'warn' THEN 1 ELSE 0 END)
            WHEN 2 THEN 'critical' WHEN 1 THEN 'warn' ELSE 'ok' END AS status,
       count_if(status = 'critical') AS critical_metrics,
       count_if(status = 'warn') AS warn_metrics,
       concat_ws(', ', collect_list(CASE WHEN status <> 'ok' THEN concat(metric, '=', value, ' (', status, ')') END)) AS breaches
FROM {fq}.dq_threshold_status
GROUP BY study_id
""")

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {fq}.dq_run_history (
  run_id STRING, recorded_at TIMESTAMP, study_id STRING, subjects_received BIGINT, subjects_clean BIGINT,
  subjects_quarantined BIGINT, pct_subjects_quarantined DOUBLE, records_received BIGINT, records_quarantined BIGINT,
  top_rule_share_pct DOUBLE, status STRING
) COMMENT 'Data quality snapshot per study at the end of every pipeline run, for trend charts'
""")
spark.sql(f"DELETE FROM {fq}.dq_run_history WHERE run_id = :run_id", args={"run_id": run_id})
spark.sql(
    f"""
    INSERT INTO {fq}.dq_run_history
    SELECT :run_id, current_timestamp(), c.study_id, c.subjects_received, c.subjects_clean, c.subjects_quarantined,
           round(100.0 * c.subjects_quarantined / nullif(c.subjects_received, 0), 1), c.records_received,
           c.records_quarantined, t.value, s.status
    FROM {fq}.dq_study_coverage c
    LEFT JOIN {fq}.dq_study_status s ON s.study_id = c.study_id
    LEFT JOIN {fq}.dq_threshold_status t ON t.study_id = c.study_id AND t.metric = 'top_rule_share_pct'
    """,
    args={"run_id": run_id},
)

status = spark.table(f"{fq}.dq_study_status").orderBy("study_id")
display(status)
critical = [r.study_id for r in status.collect() if r.status == "critical"]
warn = [r.study_id for r in status.collect() if r.status == "warn"]
dbutils.jobs.taskValues.set("critical_studies", ", ".join(critical))
dbutils.jobs.taskValues.set("warn_studies", ", ".join(warn))
print(f"Threshold check recorded for run {run_id}. critical: {critical or 'none'}; warn: {warn or 'none'}")
