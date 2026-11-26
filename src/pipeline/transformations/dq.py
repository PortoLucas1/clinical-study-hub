"""Data quality outputs, generated from the rules registry in `dq_rules.py`.

- `dq_rules`: the registry itself, so the app can explain every rule.
- `gold_dq_issues` / `gold_dq_summary`: every rule failure and observation, with rule ID, severity and action.
  The details contain the offending values, so these tables are for data managers in the app, not for Genie.
- `dq_study_coverage`: received, clean and quarantined subjects and records per study.
- `dq_reconciliation`: staged rows = bronze rows = clean rows + quarantine rows, per study and domain. It proves
  that no row was dropped between the package and the Silver layer.
"""

from functools import reduce

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from dq_rules import SUBJECT_DOMAINS, rules_rows

CATALOG = spark.conf.get("dq.catalog")
SCHEMA = spark.conf.get("dq.schema")
ALL_DOMAINS = ["study", *SUBJECT_DOMAINS]


@dp.materialized_view(name="dq_rules", comment="Data quality rules registry: rule ID, domain, severity, action (quarantine or observe) and the valid condition")
def dq_rules_table():
    return spark.createDataFrame(
        rules_rows(),
        "rule_id STRING, domain STRING, severity STRING, action STRING, description STRING, valid_condition STRING",
    )


@dp.materialized_view(
    name="gold_dq_issues",
    comment=(
        "Data quality: one row per rule failure (action = quarantine) or observation (action = observe), with "
        "subject, site and the offending value in detail. For data manager review in the app; not exposed to Genie"
    ),
    table_properties={"quality": "gold"},
)
def gold_dq_issues():
    parts = []
    for d in ALL_DOMAINS:
        df = spark.read.table(f"silver_{d}_checked")
        usubjid = F.lit(None).cast("string") if d == "study" else F.col("usubjid")
        parts.append(
            df.select(
                "study_id",
                F.lit(d.upper()).alias("domain"),
                usubjid.alias("usubjid"),
                F.explode(F.concat("quarantine_issues", "observed_issues")).alias("issue"),
            )
        )
    issues = reduce(DataFrame.unionByName, parts).select(
        "study_id", "domain", "usubjid", F.col("issue.rule_id").alias("rule_id"), F.col("issue.detail").alias("detail")
    )
    rules = spark.read.table("dq_rules").select(
        "rule_id", "domain", F.col("description").alias("rule_description"), "severity", "action"
    )
    sites = spark.read.table("silver_subject_status").select("study_id", "usubjid", "site_id")
    return (
        issues.join(rules, ["domain", "rule_id"], "left")
        .join(sites, ["study_id", "usubjid"], "left")
        .select("study_id", "domain", "rule_id", "rule_description", "severity", "action", "usubjid", "site_id", "detail")
    )


@dp.materialized_view(
    name="gold_dq_summary",
    comment="Data quality summary: issue counts by study, domain and rule (counts only, no record values)",
    table_properties={"quality": "gold"},
)
def gold_dq_summary():
    return (
        spark.read.table("gold_dq_issues")
        .groupBy("study_id", "domain", "rule_id", "rule_description", "severity", "action")
        .agg(
            F.count(F.lit(1)).alias("issue_count"),
            F.countDistinct("usubjid").alias("subjects_affected"),
            F.countDistinct("site_id").alias("sites_affected"),
        )
    )


@dp.materialized_view(
    name="dq_study_coverage",
    comment="Per study: subjects and records received, clean and quarantined. Gold KPIs cover subjects_clean only",
    table_properties={"quality": "gold"},
)
def dq_study_coverage():
    studies = spark.read.table("silver_study_checked").select("study_id").distinct()
    subjects = (
        spark.read.table("silver_subject_status")
        .groupBy("study_id")
        .agg(
            F.count(F.lit(1)).alias("subjects_received"),
            F.sum(F.when(F.col("is_clean"), 1).otherwise(0)).alias("subjects_clean"),
            F.sum(F.when(F.col("is_clean"), 0).otherwise(1)).alias("subjects_quarantined"),
        )
    )
    received = reduce(
        DataFrame.unionByName, [spark.read.table(f"silver_{d}_checked").select("study_id") for d in SUBJECT_DOMAINS]
    ).groupBy("study_id").agg(F.count(F.lit(1)).alias("records_received"))
    quarantined = reduce(
        DataFrame.unionByName, [spark.read.table(f"silver_{d}_quarantine").select("study_id") for d in SUBJECT_DOMAINS]
    ).groupBy("study_id").agg(F.count(F.lit(1)).alias("records_quarantined"))
    out = (
        studies.join(subjects, "study_id", "left")
        .join(received, "study_id", "left")
        .join(quarantined, "study_id", "left")
        .na.fill(0, ["subjects_received", "subjects_clean", "subjects_quarantined", "records_received", "records_quarantined"])
    )
    return out.withColumn(
        "pct_subjects_clean",
        F.round(F.lit(100.0) * F.col("subjects_clean") / F.when(F.col("subjects_received") > 0, F.col("subjects_received")), 1),
    )


@dp.materialized_view(
    name="dq_reconciliation",
    comment="Row reconciliation per study and domain for the latest submission: staged = bronze = clean + quarantine",
    table_properties={"quality": "gold"},
)
@dp.expect("rows_balanced", "balanced")
def dq_reconciliation():
    latest = spark.read.table("latest_submissions").select("study_id", "submission_id")
    latest_file = Window.partitionBy("submission_id", "source_file").orderBy(F.col("staged_at").desc())
    staged = (
        spark.read.table(f"{CATALOG}.{SCHEMA}.submission_files")
        .filter("status = 'staged' AND domain <> 'meta'")
        .withColumn("_rn", F.row_number().over(latest_file))
        .filter("_rn = 1")
        .join(latest, ["study_id", "submission_id"])
        .groupBy("study_id", "domain")
        .agg(F.sum("row_count").alias("staged_rows"))
    )
    counts = []
    for d in SUBJECT_DOMAINS:
        bronze = spark.read.table(f"bronze_{d}").join(latest, ["study_id", "submission_id"]).groupBy("study_id").agg(
            F.count(F.lit(1)).alias("bronze_rows")
        )
        clean = spark.read.table(f"silver_{d}").groupBy("study_id").agg(F.count(F.lit(1)).alias("clean_rows"))
        quarantine = spark.read.table(f"silver_{d}_quarantine").groupBy("study_id").agg(
            F.count(F.lit(1)).alias("quarantine_rows")
        )
        counts.append(
            bronze.join(clean, "study_id", "full").join(quarantine, "study_id", "full").withColumn("domain", F.lit(d))
        )
    rows = ["staged_rows", "bronze_rows", "clean_rows", "quarantine_rows"]
    return (
        reduce(DataFrame.unionByName, counts)
        .join(staged, ["study_id", "domain"], "full")
        .na.fill(0, rows)
        .withColumn(
            "balanced",
            (F.col("staged_rows") == F.col("bronze_rows")) & (F.col("bronze_rows") == F.col("clean_rows") + F.col("quarantine_rows")),
        )
        .select("study_id", "domain", *rows, "balanced")
    )
