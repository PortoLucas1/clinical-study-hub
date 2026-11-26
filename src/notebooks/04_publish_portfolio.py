# Databricks notebook source
# MAGIC %md
# MAGIC # 04 - Publish the study portfolio for operational serving
# MAGIC
# MAGIC Joins the Gold study KPIs (`gold_study_overview`) with the AI briefing (`gold_study_ai_summary`) into
# MAGIC one governed Delta table, `study_portfolio`, with Change Data Feed enabled. A Lakebase synced table
# MAGIC mirrors it into Postgres, so the Study Hub portfolio page is served at OLTP latency instead of
# MAGIC querying the SQL warehouse on every page view.
# MAGIC
# MAGIC After the table is merged, the task starts a refresh of the Lakebase sync pipeline (best effort: on a
# MAGIC fresh install the synced table does not exist yet and `00_install.py` creates it afterwards).

# COMMAND ----------

import re
import time

for name in ["catalog", "schema", "synced_table"]:
    dbutils.widgets.text(name, "")

catalog = dbutils.widgets.get("catalog").strip() or "clinical_demo"
schema = dbutils.widgets.get("schema").strip() or "study_onboarding"
synced_table = dbutils.widgets.get("synced_table").strip()
fq = f"{catalog}.{schema}"

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {fq}.study_portfolio (
  study_id STRING NOT NULL,
  title STRING,
  phase STRING,
  indication STRING,
  therapeutic_area STRING,
  sponsor STRING,
  planned_enrollment BIGINT,
  enrolled BIGINT,
  pct_enrollment_target DOUBLE,
  active_sites BIGINT,
  countries BIGINT,
  discontinuation_rate_pct DOUBLE,
  sae_subject_rate_pct DOUBLE,
  dq_issues BIGINT,
  dq_high_issues BIGINT,
  data_cutoff_date STRING,
  headline STRING,
  insights_generated_at STRING,
  subjects_received BIGINT,
  subjects_clean BIGINT,
  subjects_quarantined BIGINT,
  pct_subjects_clean DOUBLE,
  records_quarantined BIGINT
)
COMMENT 'One row per published study: Gold KPIs on clean subjects, data quality coverage and the AI headline. Source for the Lakebase synced table that serves the Study Hub portfolio.'
TBLPROPERTIES (delta.enableChangeDataFeed = true)
""")

COVERAGE_COLUMNS = [
    ("subjects_received", "BIGINT"),
    ("subjects_clean", "BIGINT"),
    ("subjects_quarantined", "BIGINT"),
    ("pct_subjects_clean", "DOUBLE"),
    ("records_quarantined", "BIGINT"),
]
existing = set(spark.table(f"{fq}.study_portfolio").columns)
added = [c for c, _ in COVERAGE_COLUMNS if c not in existing]
if added:
    spark.sql(
        f"ALTER TABLE {fq}.study_portfolio ADD COLUMNS ("
        + ", ".join(f"{c} {t}" for c, t in COVERAGE_COLUMNS if c in added)
        + ")"
    )
    print("Added coverage columns (recreate the Lakebase synced table to serve them):", added)

spark.sql(f"""
MERGE INTO {fq}.study_portfolio t
USING (
  SELECT
    o.study_id, o.title, o.phase, o.indication, o.therapeutic_area, o.sponsor,
    CAST(o.planned_enrollment AS BIGINT) AS planned_enrollment,
    CAST(o.enrolled AS BIGINT) AS enrolled,
    CAST(o.pct_enrollment_target AS DOUBLE) AS pct_enrollment_target,
    CAST(o.active_sites AS BIGINT) AS active_sites,
    CAST(o.countries AS BIGINT) AS countries,
    CAST(o.discontinuation_rate_pct AS DOUBLE) AS discontinuation_rate_pct,
    CAST(o.sae_subject_rate_pct AS DOUBLE) AS sae_subject_rate_pct,
    CAST(o.dq_issues AS BIGINT) AS dq_issues,
    CAST(o.dq_high_issues AS BIGINT) AS dq_high_issues,
    CAST(o.data_cutoff_date AS STRING) AS data_cutoff_date,
    a.headline,
    CAST(a.generated_at AS STRING) AS insights_generated_at,
    CAST(o.subjects_received AS BIGINT) AS subjects_received,
    CAST(o.subjects_clean AS BIGINT) AS subjects_clean,
    CAST(o.subjects_quarantined AS BIGINT) AS subjects_quarantined,
    CAST(o.pct_subjects_clean AS DOUBLE) AS pct_subjects_clean,
    CAST(o.records_quarantined AS BIGINT) AS records_quarantined
  FROM {fq}.gold_study_overview o
  LEFT JOIN {fq}.gold_study_ai_summary a USING (study_id)
) s
ON t.study_id = s.study_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
WHEN NOT MATCHED BY SOURCE THEN DELETE
""")

display(spark.sql(f"SELECT study_id, phase, enrolled, subjects_clean, subjects_received, subjects_quarantined, dq_issues, headline FROM {fq}.study_portfolio ORDER BY study_id"))

# COMMAND ----------

if not synced_table:
    print("No synced_table parameter: skipping Lakebase sync refresh.")
else:
    from databricks.sdk import WorkspaceClient

    if not re.fullmatch(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+", synced_table):
        raise ValueError(f"Invalid synced table name: {synced_table}")
    w = WorkspaceClient()
    try:
        pipelines = [
            p for p in w.pipelines.list_pipelines(filter=f"name LIKE '%{synced_table.split('.')[-1]}%'")
            if synced_table.split(".")[-1] in (p.name or "")
        ]
        if not pipelines:
            print(f"No sync pipeline found for {synced_table}; it will be created by 00_install.py.")
        for p in pipelines:
            update = w.pipelines.start_update(p.pipeline_id)
            print(f"Started sync pipeline {p.name} ({p.pipeline_id}) update {update.update_id}")
            deadline = time.time() + 600
            while time.time() < deadline:
                state = w.pipelines.get_update(p.pipeline_id, update.update_id).update.state
                print("  state:", state)
                if str(state).endswith(("COMPLETED", "FAILED", "CANCELED")):
                    break
                time.sleep(15)
    except Exception as exc:
        print("Sync refresh skipped:", exc)
