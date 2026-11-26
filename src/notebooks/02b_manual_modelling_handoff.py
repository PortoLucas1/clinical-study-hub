# Databricks notebook source
# MAGIC %md
# MAGIC # 02b - Manual data modelling hand-off
# MAGIC
# MAGIC Runs only when the AI data modelling accuracy stayed below the threshold after all retries. A job cannot pause
# MAGIC for a person, so this task is a terminal hand-off:
# MAGIC
# MAGIC 1. It records that the submission is waiting for a human in `ai_modelling_runs`.
# MAGIC 2. The task-level email notification tells the team a decision is needed.
# MAGIC 3. The run ends here: the pipeline, insights and publish tasks are skipped, so nothing unvalidated reaches Gold.
# MAGIC 4. A reviewer then starts the `manual-data-modelling` job (from the Study Hub approvals page or the Jobs UI)
# MAGIC    for this submission, which applies the mapping and runs the pipeline.
# MAGIC
# MAGIC The Study Hub shows the submission as `AWAITING_MANUAL_MODELLING` when this task has run.

# COMMAND ----------

from datetime import datetime, timezone

for name in ["submission_id", "study_id", "catalog", "schema", "ai_accuracy_threshold"]:
    dbutils.widgets.text(name, "")

submission_id = dbutils.widgets.get("submission_id").strip()
catalog = dbutils.widgets.get("catalog").strip() or "clinical_demo"
schema = dbutils.widgets.get("schema").strip() or "study_onboarding"
threshold = float(dbutils.widgets.get("ai_accuracy_threshold").strip() or 99.9)
study_id = dbutils.widgets.get("study_id").strip()
fq = f"{catalog}.{schema}"

try:
    accuracy = float(dbutils.jobs.taskValues.get(taskKey="ai_data_modelling", key="accuracy_pct", default=0.0, debugValue=0.0))
    attempts = int(dbutils.jobs.taskValues.get(taskKey="ai_data_modelling", key="attempts", default=0, debugValue=0))
    wrong = dbutils.jobs.taskValues.get(taskKey="ai_data_modelling", key="wrong_columns", default="", debugValue="")
except ValueError:
    accuracy, attempts, wrong = 0.0, 0, ""

now = datetime.now(timezone.utc)
spark.createDataFrame(
    [(submission_id, study_id, attempts + 1, "system", "", accuracy, threshold, 0, 0, wrong,
      "awaiting_manual_modelling", f"AI accuracy {accuracy}% below {threshold}% after {attempts} attempts", now)],
    "submission_id STRING, study_id STRING, attempt INT, actor STRING, scenario STRING, accuracy_pct DOUBLE, "
    "threshold_pct DOUBLE, values_checked BIGINT, values_wrong BIGINT, wrong_columns STRING, outcome STRING, "
    "feedback STRING, recorded_at TIMESTAMP",
).write.mode("append").saveAsTable(f"{fq}.ai_modelling_runs")

print(
    f"Submission {submission_id} ({study_id}) is waiting for manual data modelling: "
    f"AI accuracy {accuracy}% < {threshold}% after {attempts} attempts. Wrong columns: {wrong or 'n/a'}.\n"
    "Start the manual-data-modelling job with this submission_id once a reviewer has checked the mapping."
)
