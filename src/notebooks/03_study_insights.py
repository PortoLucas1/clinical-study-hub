# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - Generate AI study insights
# MAGIC
# MAGIC Reads the study's gold marts, asks a foundation model (via `ai_query`) for a concise
# MAGIC medical-monitoring style briefing, and upserts it into `gold_study_ai_summary`, which the
# MAGIC Study Hub app renders as "Key insights".
# MAGIC
# MAGIC The model only sees clean data: the Gold marts cover clean subjects, and data quality is passed as
# MAGIC counts (coverage and issues per rule), never as quarantined values. The output is validated before
# MAGIC it is stored; an invalid answer is replaced by a neutral message instead of raw model text.

# COMMAND ----------

import json
import re
from datetime import datetime, timezone

for name in ["submission_id", "study_id", "catalog", "schema", "llm_endpoint"]:
    dbutils.widgets.text(name, "")

catalog = dbutils.widgets.get("catalog").strip() or "clinical_demo"
schema = dbutils.widgets.get("schema").strip() or "study_onboarding"
endpoint = dbutils.widgets.get("llm_endpoint").strip() or "databricks-claude-sonnet-4-5"
submission_id = dbutils.widgets.get("submission_id").strip()
try:
    staged_study_id = dbutils.jobs.taskValues.get(taskKey="unzip_and_stage", key="study_id", default="", debugValue="")
except ValueError:  # run on its own, outside the onboarding job
    staged_study_id = ""
study_id = staged_study_id or dbutils.widgets.get("study_id").strip()
if not study_id:
    raise ValueError("study_id could not be resolved")
if not re.fullmatch(r"[A-Za-z0-9\-]+", endpoint):
    raise ValueError(f"Invalid endpoint name: {endpoint}")

fq = f"{catalog}.{schema}"
if not submission_id:  # started by the remediation job: use the study's current submission
    latest = spark.sql(f"SELECT latest_submission_id FROM {fq}.study_registry WHERE study_id = :s", args={"s": study_id}).first()
    submission_id = (latest[0] if latest else "") or ""
print(f"Generating insights for {study_id} with {endpoint}")

# COMMAND ----------


def rows(query: str, limit: int = 50) -> list[dict]:
    return [r.asDict() for r in spark.sql(query, args={"study_id": study_id}).limit(limit).collect()]


def jsonable(obj):
    return json.loads(json.dumps(obj, default=str))


context = jsonable({
    "overview": rows(f"SELECT * EXCEPT (arms) FROM {fq}.gold_study_overview WHERE study_id = :study_id", 1),
    "safety_by_arm": rows(f"SELECT * FROM {fq}.gold_ae_by_arm WHERE study_id = :study_id"),
    "top_adverse_events": rows(
        f"""SELECT arm, system_organ_class, preferred_term, events, subjects, serious_events, grade3plus_events
            FROM {fq}.gold_ae_summary WHERE study_id = :study_id ORDER BY events DESC""",
        15,
    ),
    "lab_abnormalities_post_baseline": rows(
        f"""SELECT arm, lab_test, round(avg(pct_abnormal), 1) AS avg_pct_abnormal, round(avg(mean_value), 2) AS mean_value,
                   any_value(ref_low) AS ref_low, any_value(ref_high) AS ref_high
            FROM {fq}.gold_lab_abnormalities WHERE study_id = :study_id AND visitnum >= 2
            GROUP BY arm, lab_test ORDER BY avg_pct_abnormal DESC""",
        16,
    ),
    "site_performance": rows(
        f"""SELECT site_id, country, enrolled, discontinuation_rate_pct, saes, pct_visits_out_of_window, dq_issues
            FROM {fq}.gold_site_performance WHERE study_id = :study_id ORDER BY dq_issues DESC, discontinuation_rate_pct DESC""",
        12,
    ),
    "data_quality_coverage": rows(
        f"""SELECT subjects_received, subjects_clean, subjects_quarantined, pct_subjects_clean, records_received, records_quarantined
            FROM {fq}.dq_study_coverage WHERE study_id = :study_id""",
        1,
    ),
    "data_quality_rule_counts": rows(
        f"""SELECT domain, rule_id, rule_description, action, issue_count, subjects_affected
            FROM {fq}.gold_dq_summary WHERE study_id = :study_id ORDER BY issue_count DESC""",
        20,
    ),
})
coverage = (context["data_quality_coverage"] or [{}])[0]

# COMMAND ----------

prompt = f"""You are a clinical data scientist preparing a study briefing for the medical monitor and
clinical operations lead of study {study_id}. All data is synthetic. Using ONLY the JSON metrics below,
return a single JSON object (no markdown fences) with exactly these keys:
  "headline": one sentence (max 25 words) with the most important takeaway,
  "summary": 3-4 sentence narrative covering enrollment, safety and data quality,
  "findings": array of 4-6 objects {{"category": one of ["Enrollment","Safety","Labs","Operations","Data Quality"],
              "severity": one of ["info","watch","action"], "title": short title, "detail": one or two sentences citing numbers}},
  "recommended_actions": array of 3-4 short, concrete next steps.
Compare treatment arms when relevant (e.g. lab shifts or SAE rates in the investigational arm vs control).
Data quality context: every metric covers CLEAN subjects only ({coverage.get('subjects_clean')} of
{coverage.get('subjects_received')} received). Records that failed a data quality rule, and all records of the
affected subjects, are quarantined for data management review and are NOT in these metrics. Mention this coverage
once in the summary, use the rule counts only to describe data quality, and never speculate about quarantined values.

METRICS:
{json.dumps(context)}
"""

CATEGORIES = {"Enrollment", "Safety", "Labs", "Operations", "Data Quality"}
SEVERITIES = {"info", "watch", "action"}


def validate(obj) -> list[str]:
    errors = []
    if not isinstance(obj, dict):
        return ["not a JSON object"]
    for key in ("headline", "summary"):
        if not isinstance(obj.get(key), str) or not obj[key].strip():
            errors.append(f"{key} missing")
    findings = obj.get("findings")
    if not isinstance(findings, list) or not findings:
        errors.append("findings missing")
    else:
        for i, f in enumerate(findings):
            if not isinstance(f, dict):
                errors.append(f"finding {i} not an object")
                continue
            if f.get("category") not in CATEGORIES:
                errors.append(f"finding {i} category {f.get('category')!r}")
            if f.get("severity") not in SEVERITIES:
                errors.append(f"finding {i} severity {f.get('severity')!r}")
            if not f.get("title") or not f.get("detail"):
                errors.append(f"finding {i} title/detail missing")
    actions = obj.get("recommended_actions")
    if not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
        errors.append("recommended_actions missing")
    return errors


raw = spark.sql(f"SELECT ai_query('{endpoint}', :prompt) AS r", args={"prompt": prompt}).first()["r"]
match = re.search(r"\{.*\}", raw, re.S)
try:
    parsed = json.loads(match.group(0) if match else raw)
except json.JSONDecodeError:
    parsed = None
errors = validate(parsed) if parsed is not None else ["response is not valid JSON"]
validation_status = "valid" if not errors else "invalid: " + "; ".join(errors)[:500]
if errors:
    parsed = {
        "headline": f"AI briefing unavailable for {study_id}: the model output failed validation",
        "summary": "The briefing will be regenerated on the next run. KPIs and data quality results are unaffected.",
        "findings": [],
        "recommended_actions": [],
    }

print("validation:", validation_status)
print(json.dumps(parsed, indent=2)[:3000])

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {fq}.gold_study_ai_summary (
  study_id STRING, submission_id STRING, headline STRING, summary STRING,
  findings_json STRING, recommended_actions_json STRING, model STRING, generated_at TIMESTAMP
) COMMENT 'AI-generated study briefing (headline, findings, recommended actions) per study, from clean data only'
""")
existing = set(spark.table(f"{fq}.gold_study_ai_summary").columns)
for col, dtype in [("subjects_clean", "BIGINT"), ("subjects_received", "BIGINT"), ("validation_status", "STRING")]:
    if col not in existing:
        spark.sql(f"ALTER TABLE {fq}.gold_study_ai_summary ADD COLUMNS ({col} {dtype})")

out = spark.createDataFrame(
    [(
        study_id, submission_id, parsed.get("headline", ""), parsed.get("summary", ""),
        json.dumps(parsed.get("findings", [])), json.dumps(parsed.get("recommended_actions", [])),
        endpoint, datetime.now(timezone.utc),
        coverage.get("subjects_clean"), coverage.get("subjects_received"), validation_status,
    )],
    "study_id STRING, submission_id STRING, headline STRING, summary STRING, findings_json STRING, recommended_actions_json STRING, model STRING, generated_at TIMESTAMP, subjects_clean BIGINT, subjects_received BIGINT, validation_status STRING",
)
out.createOrReplaceTempView("new_summary")
spark.sql(f"""
MERGE INTO {fq}.gold_study_ai_summary t USING new_summary s ON t.study_id = s.study_id
WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *
""")
print("Insights saved")
