# Databricks notebook source
# MAGIC %md
# MAGIC # 06 - Apply reviewed quarantine decisions
# MAGIC
# MAGIC First task of the `quarantine-remediation` job, which the data management team starts on demand, independently
# MAGIC of the onboarding flow, when they have finished reviewing a study's quarantined records in the Study Hub.
# MAGIC
# MAGIC Quarantine is derived: the Lakeflow Declarative Pipelines recompute it from the data on every update, so moving
# MAGIC rows back by hand would not stick. Instead, issues a reviewer **accepted** are recorded as waivers:
# MAGIC
# MAGIC 1. Wait until the pipeline is idle (it allows one active update, and the onboarding job uses the same one).
# MAGIC 2. Read the `accepted` decisions of the study from the Lakebase table `study_hub.dq_issue_reviews`
# MAGIC    (read-only, through the Lakebase catalog).
# MAGIC 3. Add them to `dq_waivers`, tied to the study's current submission. A resubmitted package is reviewed again.
# MAGIC 4. The pipeline runs next. A waived rule no longer quarantines the record, and a subject returns to Gold only
# MAGIC    when every one of its issues is resolved. Raw data is never modified; `dq_waivers` is the audit trail.
# MAGIC
# MAGIC Records that need a corrected value are fixed at the source and resubmitted, which supersedes the old package.

# COMMAND ----------

import re
import time

for name in ["catalog", "schema", "study_id", "lakebase_catalog", "pipeline_id"]:
    dbutils.widgets.text(name, "")

catalog = dbutils.widgets.get("catalog").strip() or "clinical_demo"
schema = dbutils.widgets.get("schema").strip() or "study_onboarding"
study_id = dbutils.widgets.get("study_id").strip()
lakebase_catalog = dbutils.widgets.get("lakebase_catalog").strip() or "study_hub_lakebase"
pipeline_id = dbutils.widgets.get("pipeline_id").strip()
if not study_id:
    raise ValueError("study_id is required: remediation runs for one study at a time")
if not re.fullmatch(r"[A-Za-z0-9_]+", lakebase_catalog):
    raise ValueError(f"Invalid catalog name: {lakebase_catalog}")
fq = f"{catalog}.{schema}"

# COMMAND ----------

# 1. Wait for the pipeline to be idle.
if pipeline_id:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    deadline = time.time() + 20 * 60
    while True:
        state = str(w.pipelines.get(pipeline_id).state)
        if state.endswith(("IDLE", "FAILED", "DELETED")) or time.time() > deadline:
            break
        print(f"Pipeline is {state}; waiting for the active update to finish...")
        time.sleep(15)
    print("Pipeline state:", state)

# COMMAND ----------

# 2-3. Accepted reviews -> waivers for the current submission.
registry = spark.sql(f"SELECT latest_submission_id FROM {fq}.study_registry WHERE study_id = :s", args={"s": study_id}).first()
if registry is None or not registry[0]:
    raise ValueError(f"Study {study_id} is not onboarded")
submission_id = registry[0]

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {fq}.dq_waivers (
  study_id STRING, submission_id STRING, domain STRING, rule_id STRING, usubjid STRING,
  accepted_by STRING, accepted_at TIMESTAMP, comment STRING
)""")
before = spark.sql(
    f"SELECT subjects_clean, subjects_quarantined, subjects_received FROM {fq}.dq_study_coverage WHERE study_id = :s",
    args={"s": study_id},
).first()
waivers_before = spark.table(f"{fq}.dq_waivers").filter(f"study_id = '{study_id}'").count()

spark.sql(
    f"""
    SELECT r.study_id, :sub AS submission_id, upper(r.domain) AS domain, r.rule_id, r.usubjid,
           r.reviewed_by AS accepted_by, r.reviewed_at AS accepted_at, r.comment
    FROM {lakebase_catalog}.study_hub.dq_issue_reviews r
    JOIN {fq}.dq_rules q ON upper(q.domain) = upper(r.domain) AND q.rule_id = r.rule_id AND q.action = 'quarantine'
    WHERE r.study_id = :s AND r.status = 'accepted' AND r.usubjid IS NOT NULL AND r.usubjid <> ''
    """,
    args={"s": study_id, "sub": submission_id},
).createOrReplaceTempView("accepted_reviews")
spark.sql(f"""
MERGE INTO {fq}.dq_waivers t USING accepted_reviews s
ON t.study_id = s.study_id AND t.submission_id = s.submission_id AND t.domain = s.domain
   AND t.rule_id = s.rule_id AND t.usubjid = s.usubjid
WHEN NOT MATCHED THEN INSERT *
""")
waivers_after = spark.table(f"{fq}.dq_waivers").filter(f"study_id = '{study_id}'").count()
added = waivers_after - waivers_before

print(f"{study_id} submission {submission_id}: {added} new waiver(s), {waivers_after} in total")
if added == 0:
    print("No newly accepted issues: nothing changes. Accept issues in the Study Hub (Quarantine tab) first.")

dbutils.jobs.taskValues.set("study_id", study_id)
dbutils.jobs.taskValues.set("waivers_added", int(added))
dbutils.jobs.taskValues.set("subjects_clean_before", int(before["subjects_clean"]) if before else 0)
dbutils.jobs.taskValues.set("subjects_quarantined_before", int(before["subjects_quarantined"]) if before else 0)
