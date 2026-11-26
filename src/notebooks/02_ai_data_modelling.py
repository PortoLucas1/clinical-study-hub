# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - AI data modelling (MOCK)
# MAGIC
# MAGIC Stands in for an AI step that maps the vendor and EDC columns of the staged package to SDTM variables
# MAGIC before the Lakeflow Declarative Pipelines run. The AI proposal is **simulated** (deterministic, selected by
# MAGIC the `ai_demo_scenario` job parameter: `pass`, `recover` or `fail`); the validation against the golden
# MAGIC mapping, the accuracy calculation and the retry loop are real.
# MAGIC
# MAGIC - Accuracy is value-weighted (each mapped column counts once per row of its file).
# MAGIC - The step retries up to `ai_max_retries` times, telling the model which columns were wrong.
# MAGIC - Every attempt is recorded in `ai_modelling_runs`.
# MAGIC - The final accuracy is published as the task value `accuracy_pct`. The next task, `modelling_accuracy_gate`,
# MAGIC   continues the pipeline when it meets `ai_accuracy_threshold` and otherwise routes to the manual fallback.

# COMMAND ----------

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

for name in ["submission_id", "study_id", "catalog", "schema", "ai_demo_scenario", "ai_accuracy_threshold", "ai_max_retries"]:
    dbutils.widgets.text(name, "")

submission_id = dbutils.widgets.get("submission_id").strip()
catalog = dbutils.widgets.get("catalog").strip() or "clinical_demo"
schema = dbutils.widgets.get("schema").strip() or "study_onboarding"
scenario = dbutils.widgets.get("ai_demo_scenario").strip().lower() or "pass"
threshold = float(dbutils.widgets.get("ai_accuracy_threshold").strip() or 99.9)
max_retries = int(dbutils.widgets.get("ai_max_retries").strip() or 3)
try:
    study_id = dbutils.jobs.taskValues.get(taskKey="unzip_and_stage", key="study_id", default="", debugValue="")
except ValueError:  # run on its own, outside the onboarding job
    study_id = ""
study_id = study_id or dbutils.widgets.get("study_id").strip()
if not submission_id or not study_id:
    raise ValueError("submission_id and study_id are required")
fq = f"{catalog}.{schema}"

# Make src/lib importable (the modelling logic is plain Python so it can be unit tested).
try:
    nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    lib_dir = Path("/Workspace" + nb_path).parent.parent / "lib"
except Exception:
    lib_dir = Path(os.getcwd()).parent / "lib"
sys.path.insert(0, str(lib_dir))
from modelling import run_modelling  # noqa: E402

print(f"study={study_id} submission={submission_id} scenario={scenario} threshold={threshold} max_retries={max_retries}")

# COMMAND ----------

# What was staged for this submission: columns (header of each staged CSV) and rows per domain.
files = (
    spark.table(f"{fq}.submission_files")
    .filter(f"submission_id = '{submission_id}' AND status = 'staged' AND domain NOT IN ('meta', 'unrecognized')")
    .select("domain", "staged_path", "row_count")
    .collect()
)
domain_columns: dict[str, list[str]] = {}
rows_by_domain: dict[str, int] = {}
for f in files:
    domain_columns.setdefault(f.domain, [])
    for c in pd.read_csv(f.staged_path, nrows=0).columns:
        if c not in domain_columns[f.domain]:
            domain_columns[f.domain].append(c)
    rows_by_domain[f.domain] = rows_by_domain.get(f.domain, 0) + int(f.row_count or 0)
if not domain_columns:
    raise ValueError(f"No staged files found for submission {submission_id}")
print({d: (len(c), rows_by_domain[d]) for d, c in domain_columns.items()})

result = run_modelling(domain_columns, rows_by_domain, scenario, threshold, max_retries, seed=study_id)
for a in result.attempts:
    print(f"attempt {a.attempt}: accuracy {a.accuracy_pct}% ({a.values_wrong}/{a.values_checked} wrong values) -> {a.outcome}"
          + (f" | wrong: {', '.join(a.wrong_columns)}" if a.wrong_columns else ""))

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {fq}.ai_modelling_runs (
  submission_id STRING, study_id STRING, attempt INT, actor STRING, scenario STRING,
  accuracy_pct DOUBLE, threshold_pct DOUBLE, values_checked BIGINT, values_wrong BIGINT,
  wrong_columns STRING, outcome STRING, feedback STRING, recorded_at TIMESTAMP
) COMMENT 'Data modelling attempts per submission: AI proposals (mock) and the human-approved mapping when the fallback is used'
""")
# A repaired run replaces its previous AI attempts; human decisions are kept.
spark.sql(f"DELETE FROM {fq}.ai_modelling_runs WHERE submission_id = '{submission_id}' AND actor = 'ai'")
now = datetime.now(timezone.utc)
spark.createDataFrame(
    [
        (submission_id, study_id, a.attempt, "ai", a.scenario, float(a.accuracy_pct), float(threshold), int(a.values_checked),
         int(a.values_wrong), ", ".join(a.wrong_columns), a.outcome, a.feedback, now)
        for a in result.attempts
    ],
    "submission_id STRING, study_id STRING, attempt INT, actor STRING, scenario STRING, accuracy_pct DOUBLE, "
    "threshold_pct DOUBLE, values_checked BIGINT, values_wrong BIGINT, wrong_columns STRING, outcome STRING, "
    "feedback STRING, recorded_at TIMESTAMP",
).write.mode("append").saveAsTable(f"{fq}.ai_modelling_runs")

final = result.final
dbutils.jobs.taskValues.set("accuracy_pct", float(final.accuracy_pct))
dbutils.jobs.taskValues.set("attempts", len(result.attempts))
dbutils.jobs.taskValues.set("passed", bool(result.passed))
dbutils.jobs.taskValues.set("wrong_columns", ", ".join(final.wrong_columns))
print(f"Final accuracy {final.accuracy_pct}% after {len(result.attempts)} attempt(s): "
      + ("meets the threshold, pipeline continues" if result.passed else "below the threshold, routing to manual modelling"))
