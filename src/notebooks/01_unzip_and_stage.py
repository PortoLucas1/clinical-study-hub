# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Unzip and stage an approved study package
# MAGIC
# MAGIC Lakeflow Declarative Pipelines ingest CSV/JSON natively but cannot open zip archives or Excel
# MAGIC workbooks, so this task:
# MAGIC 1. Validates the approved package (`study_metadata.json` present, study id matches, required domains
# MAGIC    present). The required domains match the checks in the app.
# MAGIC 2. Extracts each file into `raw/<study_id>/<domain>/<submission_id>__<file>.csv`.
# MAGIC 3. Converts vendor Excel files to CSV with normalized headers, and records any missing required column.
# MAGIC    Rows are never dropped here: rows with missing values are quarantined by the pipeline rules.
# MAGIC 4. Keeps unrecognized files in `raw/<study_id>/unrecognized/` for review instead of discarding them.
# MAGIC 5. Records the package in `study_registry` and `submission_files`.

# COMMAND ----------

# MAGIC %pip install openpyxl --quiet

# COMMAND ----------

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

for name in ["submission_id", "study_id", "zip_path", "catalog", "schema"]:
    dbutils.widgets.text(name, "")

submission_id = dbutils.widgets.get("submission_id").strip()
study_id_param = dbutils.widgets.get("study_id").strip()
zip_path = dbutils.widgets.get("zip_path").strip()
catalog = dbutils.widgets.get("catalog").strip() or "clinical_demo"
schema = dbutils.widgets.get("schema").strip() or "study_onboarding"

if not submission_id or not zip_path:
    raise ValueError("submission_id and zip_path are required job parameters")

raw_root = Path(f"/Volumes/{catalog}/{schema}/raw")
print(f"submission={submission_id} study={study_id_param or '<from metadata>'} zip={zip_path}")

# COMMAND ----------

DOMAIN_BY_STEM = {
    "demographics": "dm",
    "adverse_events": "ae",
    "vital_signs": "vs",
    "exposure": "ex",
    "disposition": "ds",
    "site_visits": "sv",
    "central_lab_results": "lb",
    "labs": "lb",
}

REQUIRED_DOMAINS = ["dm", "ae", "lb"]
REQUIRED_COLUMNS = {
    "dm": ["SUBJECT_ID", "SITE_ID", "ARM", "AGE", "CONSENT_DATE", "RANDOMIZATION_DATE"],
    "ae": ["SUBJECT_ID", "AE_TERM", "SEVERITY_GRADE", "SERIOUS", "ONSET_DATE"],
    "vs": ["SUBJECT_ID", "VISIT", "VISIT_DATE", "TEST", "RESULT", "UNIT"],
    "lb": ["PATIENT", "LAB_TEST", "RESULT_VALUE", "UNITS", "REF_LOW", "REF_HIGH", "COLLECTION_DATE", "VISIT"],
    "ex": ["SUBJECT_ID", "TREATMENT", "START_DATE"],
    "ds": ["SUBJECT_ID", "STATUS"],
    "sv": ["SUBJECT_ID", "VISIT", "PLANNED_DATE", "ACTUAL_DATE"],
}


def normalize_header(col: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(col).strip().upper()).strip("_")


with open(zip_path, "rb") as fh:
    archive = zipfile.ZipFile(io.BytesIO(fh.read()))

members = [m for m in archive.infolist() if not m.is_dir() and not Path(m.filename).name.startswith(".")]
meta_member = next((m for m in members if Path(m.filename).name == "study_metadata.json"), None)
if meta_member is None:
    raise ValueError("Package rejected: study_metadata.json is missing")

metadata = json.loads(archive.read(meta_member))
study_id = metadata.get("study_id", "").strip()
if study_id_param and study_id_param != study_id:
    raise ValueError(f"Package study_id '{study_id}' does not match submission study_id '{study_id_param}'")
declared = {Path(k).stem: v.get("domain") for k, v in metadata.get("files", {}).items()}

# COMMAND ----------

def keep_unrecognized(member, reason: str) -> None:
    """Copies a file the pipeline cannot use to raw/<study>/unrecognized/, so nothing in the package is lost."""
    target = raw_root / study_id / "unrecognized" / f"{submission_id}__{Path(member.filename).name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive.read(member))
    staged.append(("unrecognized", member.filename, target.as_posix(), 0, reason, None))


staged = []
for m in members:
    src = Path(m.filename)
    stem, suffix = src.stem.lower(), src.suffix.lower()
    if src.name == "study_metadata.json":
        target = raw_root / study_id / "meta" / f"{submission_id}__study_metadata.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        meta_out = {k: v for k, v in metadata.items() if k != "files"}
        meta_out.update(submission_id=submission_id, staged_at=datetime.now(timezone.utc).isoformat())
        target.write_text(json.dumps(meta_out))
        staged.append(("meta", src.as_posix(), target.as_posix(), 1, "staged", None))
        continue

    domain = DOMAIN_BY_STEM.get(stem) or declared.get(src.stem)
    if not domain:
        keep_unrecognized(m, "kept for review: unrecognized file")
        continue

    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(io.BytesIO(archive.read(m)), dtype=str)
    elif suffix == ".csv":
        df = pd.read_csv(io.BytesIO(archive.read(m)), dtype=str, keep_default_na=False)
    else:
        keep_unrecognized(m, f"kept for review: unsupported format {suffix}")
        continue
    target = raw_root / study_id / domain / f"{submission_id}__{stem}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    df.columns = [normalize_header(c) for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS.get(domain, []) if c not in df.columns]
    df.to_csv(target, index=False)
    staged.append((domain, src.as_posix(), target.as_posix(), len(df), "staged", ", ".join(missing) or None))

for row in staged:
    print(row)

present = {s[0] for s in staged if s[4] == "staged"}
missing_domains = [d for d in REQUIRED_DOMAINS if d not in present]
if missing_domains:
    raise ValueError(f"Package rejected: required domain files missing: {', '.join(missing_domains)}")
for s in staged:
    if s[5]:
        print(f"WARNING {s[1]}: missing required columns {s[5]}; affected rows will be quarantined by the pipeline")

# COMMAND ----------

now = datetime.now(timezone.utc)
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.study_registry (
  study_id STRING, nct_id STRING, title STRING, phase STRING, indication STRING,
  therapeutic_area STRING, sponsor STRING, planned_enrollment INT,
  latest_submission_id STRING, files_staged INT, rows_staged BIGINT, staged_at TIMESTAMP
) COMMENT 'Operational registry of onboarded studies and their latest approved package'
""")
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.dq_waivers (
  study_id STRING, submission_id STRING, domain STRING, rule_id STRING, usubjid STRING,
  accepted_by STRING, accepted_at TIMESTAMP, comment STRING
) COMMENT 'Data quality issues a data manager accepted (waived) for a subject. The Silver layer no longer quarantines a record for a waived rule. Written by the quarantine_remediation job; tied to the submission it was accepted for'
""")
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.dq_remediation_log (
  run_id STRING, study_id STRING, waivers_added BIGINT, subjects_clean_before BIGINT, subjects_clean_after BIGINT,
  subjects_quarantined_before BIGINT, subjects_quarantined_after BIGINT, unbalanced_domains BIGINT, recorded_at TIMESTAMP
) COMMENT 'Outcome of every quarantine remediation run: subjects returned to Gold and the reconciliation check'
""")
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.submission_files (
  submission_id STRING, study_id STRING, domain STRING, source_file STRING,
  staged_path STRING, row_count BIGINT, status STRING, staged_at TIMESTAMP
) COMMENT 'File-level manifest of every staged study package'
""")

files_df = spark.createDataFrame(
    [(submission_id, study_id, d, s, t, int(n), st, now, miss) for d, s, t, n, st, miss in staged],
    "submission_id STRING, study_id STRING, domain STRING, source_file STRING, staged_path STRING, row_count BIGINT, status STRING, staged_at TIMESTAMP, missing_columns STRING",
)
files_df.write.mode("append").option("mergeSchema", "true").saveAsTable(f"{catalog}.{schema}.submission_files")

staged_ok = [s for s in staged if s[4] == "staged" and s[0] != "meta"]
dbutils.jobs.taskValues.set("unrecognized_files", len([s for s in staged if s[0] == "unrecognized"]))
reg = spark.createDataFrame(
    [(
        study_id, metadata.get("nct_id"), metadata.get("title"), metadata.get("phase"),
        metadata.get("indication"), metadata.get("therapeutic_area"), metadata.get("sponsor"),
        int(metadata.get("planned_enrollment") or 0), submission_id,
        len(staged_ok), int(sum(s[3] for s in staged_ok)), now,
    )],
    "study_id STRING, nct_id STRING, title STRING, phase STRING, indication STRING, therapeutic_area STRING, sponsor STRING, planned_enrollment INT, latest_submission_id STRING, files_staged INT, rows_staged BIGINT, staged_at TIMESTAMP",
)
reg.createOrReplaceTempView("incoming_registry")
spark.sql(f"""
MERGE INTO {catalog}.{schema}.study_registry t USING incoming_registry s ON t.study_id = s.study_id
WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *
""")

dbutils.jobs.taskValues.set("study_id", study_id)
print(f"Staged {len(staged_ok)} files for {study_id}")
