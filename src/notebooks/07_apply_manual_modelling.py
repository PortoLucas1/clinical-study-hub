# Databricks notebook source
# MAGIC %md
# MAGIC # 07 - Apply the manual data modelling (MOCK)
# MAGIC
# MAGIC First task of the `manual-data-modelling` job, the human-in-the-loop fallback for submissions whose AI data
# MAGIC modelling stayed below the accuracy threshold. A reviewer starts the job (from the Study Hub approvals page or the
# MAGIC Jobs UI) after checking the mapping. This mock applies the reviewed golden mapping, records the decision in
# MAGIC `ai_modelling_runs` (`actor = human`), and the job continues with the same pipeline, threshold check,
# MAGIC insights and publish tasks as the automatic flow.

# COMMAND ----------

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

for name in ["submission_id", "study_id", "catalog", "schema", "reviewer"]:
    dbutils.widgets.text(name, "")

submission_id = dbutils.widgets.get("submission_id").strip()
study_id = dbutils.widgets.get("study_id").strip()
catalog = dbutils.widgets.get("catalog").strip() or "clinical_demo"
schema = dbutils.widgets.get("schema").strip() or "study_onboarding"
reviewer = dbutils.widgets.get("reviewer").strip() or spark.sql("SELECT current_user()").first()[0]
if not submission_id or not study_id:
    raise ValueError("submission_id and study_id are required")
fq = f"{catalog}.{schema}"

try:
    nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    lib_dir = Path("/Workspace" + nb_path).parent.parent / "lib"
except Exception:
    lib_dir = Path(os.getcwd()).parent / "lib"
sys.path.insert(0, str(lib_dir))
from modelling import golden_mapping, validate  # noqa: E402

# COMMAND ----------

waiting = spark.sql(
    f"""SELECT count(*) FROM {fq}.ai_modelling_runs
        WHERE submission_id = :s AND outcome = 'awaiting_manual_modelling'""",
    args={"s": submission_id},
).first()[0]
if not waiting:
    print(f"WARNING: submission {submission_id} was not waiting for manual modelling; applying the mapping anyway")

files = (
    spark.table(f"{fq}.submission_files")
    .filter(f"submission_id = '{submission_id}' AND status = 'staged' AND domain NOT IN ('meta', 'unrecognized')")
    .select("domain", "staged_path", "row_count")
    .collect()
)
if not files:
    raise ValueError(f"No staged files found for submission {submission_id}")
domain_columns: dict[str, list[str]] = {}
rows_by_domain: dict[str, int] = {}
for f in files:
    cols = domain_columns.setdefault(f.domain, [])
    cols.extend(c for c in pd.read_csv(f.staged_path, nrows=0).columns if c not in cols)
    rows_by_domain[f.domain] = rows_by_domain.get(f.domain, 0) + int(f.row_count or 0)

golden = golden_mapping(domain_columns)
v = validate(dict(golden), golden, rows_by_domain)  # the reviewed mapping is the golden spec
now = datetime.now(timezone.utc)
spark.createDataFrame(
    [(submission_id, study_id, 0, "human", "", float(v.accuracy_pct), 0.0, int(v.values_checked), int(v.values_wrong), "",
      "human_approved", f"Mapping reviewed and applied by {reviewer}", now)],
    "submission_id STRING, study_id STRING, attempt INT, actor STRING, scenario STRING, accuracy_pct DOUBLE, "
    "threshold_pct DOUBLE, values_checked BIGINT, values_wrong BIGINT, wrong_columns STRING, outcome STRING, "
    "feedback STRING, recorded_at TIMESTAMP",
).write.mode("append").saveAsTable(f"{fq}.ai_modelling_runs")
dbutils.jobs.taskValues.set("study_id", study_id)
print(f"Manual modelling applied by {reviewer} for {study_id}: {len(golden)} columns mapped, accuracy {v.accuracy_pct}%")
