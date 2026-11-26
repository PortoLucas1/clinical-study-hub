# Databricks notebook source
# MAGIC %md
# MAGIC # 06b - Remediation summary
# MAGIC
# MAGIC Last task of the `quarantine-remediation` job. Compares the study before and after the pipeline refresh,
# MAGIC records the outcome in `dq_remediation_log`, and fails when reconciliation no longer balances, because that
# MAGIC would mean rows went missing.

# COMMAND ----------

from datetime import datetime, timezone

for name in ["catalog", "schema", "study_id", "run_id"]:
    dbutils.widgets.text(name, "")

catalog = dbutils.widgets.get("catalog").strip() or "clinical_demo"
schema = dbutils.widgets.get("schema").strip() or "study_onboarding"
study_id = dbutils.widgets.get("study_id").strip()
run_id = dbutils.widgets.get("run_id").strip()
fq = f"{catalog}.{schema}"


def before(key, default=0):
    try:
        return int(dbutils.jobs.taskValues.get(taskKey="apply_reviews", key=key, default=default, debugValue=default))
    except ValueError:
        return default


waivers_added = before("waivers_added")
clean_before = before("subjects_clean_before")
quarantined_before = before("subjects_quarantined_before")

after = spark.sql(
    f"SELECT subjects_clean, subjects_quarantined, subjects_received FROM {fq}.dq_study_coverage WHERE study_id = :s",
    args={"s": study_id},
).first()
unbalanced = spark.sql(
    f"SELECT count(*) FROM {fq}.dq_reconciliation WHERE study_id = :s AND NOT balanced", args={"s": study_id}
).first()[0]

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {fq}.dq_remediation_log (
  run_id STRING, study_id STRING, waivers_added BIGINT, subjects_clean_before BIGINT, subjects_clean_after BIGINT,
  subjects_quarantined_before BIGINT, subjects_quarantined_after BIGINT, unbalanced_domains BIGINT, recorded_at TIMESTAMP
) COMMENT 'Outcome of every quarantine remediation run: subjects returned to Gold and the reconciliation check'
""")
spark.createDataFrame(
    [(run_id, study_id, waivers_added, clean_before, int(after["subjects_clean"]), quarantined_before,
      int(after["subjects_quarantined"]), int(unbalanced), datetime.now(timezone.utc))],
    "run_id STRING, study_id STRING, waivers_added BIGINT, subjects_clean_before BIGINT, subjects_clean_after BIGINT, "
    "subjects_quarantined_before BIGINT, subjects_quarantined_after BIGINT, unbalanced_domains BIGINT, recorded_at TIMESTAMP",
).write.mode("append").saveAsTable(f"{fq}.dq_remediation_log")

print(
    f"{study_id}: {waivers_added} waiver(s) applied. Clean subjects {clean_before} -> {after['subjects_clean']}, "
    f"quarantined {quarantined_before} -> {after['subjects_quarantined']}, unbalanced domains: {unbalanced}"
)
if unbalanced:
    raise RuntimeError(f"Reconciliation failed for {study_id}: {unbalanced} domain(s) do not balance")
