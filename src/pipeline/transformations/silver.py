"""Silver: standardized, SDTM-like study domains with quarantine-first data quality.

Raw EDC and vendor columns are mapped to SDTM-style variables (USUBJID, AETERM, LBTESTCD, ...) and typed.
No row is ever dropped. For each domain:

- `silver_<d>_checked` (private) holds every row of the latest approved submission, with the rules from
  `dq_rules.py` applied as warn-only expectations (metrics in the event log) and the failures recorded per row.
- `silver_subject_status` marks a subject clean only when none of its records, in any domain, failed a
  quarantine rule.
- `silver_<d>` holds valid records of clean subjects. Gold, Genie and the AI insights read only these tables.
- `silver_<d>_quarantine` holds everything else: records that failed a rule, plus every record of a flagged
  subject (`SUBJECT_CASCADE`). Data managers review them in the Study Hub app.
"""

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from dq_rules import OBSERVE, QUARANTINE, SUBJECT_DOMAINS, expectations, issues_sql

CATALOG = spark.conf.get("dq.catalog")
SCHEMA = spark.conf.get("dq.schema")

VISIT_ORDER = {"SCREENING": 0, "BASELINE": 1, "WEEK 4": 2, "WEEK 8": 3, "WEEK 12": 4, "WEEK 24": 5}

CHECK_COLUMNS = ["quarantine_issues", "observed_issues", "failed_rules", "is_record_valid"]
HELPERS = {
    "study": [],
    "dm": ["dup_count", "data_cutoff_date"],
    "ae": ["in_dm", "randdt", "data_cutoff_date"],
    "vs": ["in_dm", "data_cutoff_date"],
    "lb": ["in_dm", "study_unit", "data_cutoff_date"],
    "ex": ["in_dm", "data_cutoff_date"],
    "ds": ["in_dm", "data_cutoff_date"],
    "sv": ["in_dm", "data_cutoff_date"],
}
DESCRIPTIONS = {
    "study": "study protocol metadata (one row per study)",
    "dm": "SDTM-like DM (Demographics): one row per subject",
    "ae": "SDTM-like AE (Adverse Events): one row per reported event",
    "vs": "SDTM-like VS (Vital Signs): one row per measurement",
    "lb": "SDTM-like LB (Laboratory): central lab vendor results mapped to SDTM variables",
    "ex": "SDTM-like EX (Exposure): study treatment administration per subject",
    "ds": "SDTM-like DS (Disposition): current status per subject",
    "sv": "SDTM-like SV (Subject Visits): planned vs actual visit dates",
}


def src(df: DataFrame, col: str):
    """Trimmed source column, NULL when blank or absent (a missing column is quarantined, never a crash)."""
    if col not in df.columns:
        return F.lit(None).cast("string")
    return F.when(F.trim(F.col(col)) == "", F.lit(None)).otherwise(F.trim(F.col(col)))


def as_date(raw_col: str) -> str:
    return f"try_cast(substr({raw_col}, 1, 10) AS DATE)"


def visitnum(col: str) -> str:
    return "CASE " + " ".join(f"WHEN upper({col}) = '{k}' THEN {v}" for k, v in VISIT_ORDER.items()) + " END"


@dp.temporary_view(name="latest_submissions")
def latest_submissions():
    """Latest approved submission per study, chosen by ingestion time (not by the submission id string)."""
    w = Window.partitionBy("study_id").orderBy(F.col("_ingested_at").desc(), F.col("submission_id").desc())
    return (
        spark.read.table("bronze_study_metadata")
        .select("study_id", "submission_id", "_ingested_at", F.col("data_cutoff_date").cast("date").alias("data_cutoff_date"))
        .withColumn("_rn", F.row_number().over(w))
        .filter("_rn = 1")
        .select("study_id", "submission_id", "data_cutoff_date")
    )


def latest(table: str, with_cutoff: bool = True) -> DataFrame:
    keys = spark.read.table("latest_submissions")
    if not with_cutoff:
        keys = keys.select("study_id", "submission_id")
    return spark.read.table(table).join(keys, ["study_id", "submission_id"])


def waived_rules(domain: str) -> DataFrame:
    """Rules a data manager accepted for a subject (dq_waivers, written by the quarantine_remediation job).

    A waiver is tied to the submission it was accepted for, so a resubmitted package is reviewed again."""
    return (
        spark.read.table(f"{CATALOG}.{SCHEMA}.dq_waivers")
        .filter(F.col("domain") == domain.upper())
        .groupBy("study_id", "submission_id", "usubjid")
        .agg(F.collect_set("rule_id").alias("waived_rules"))
    )


def checked(df: DataFrame, domain: str) -> DataFrame:
    out = df.withColumn("quarantine_issues", F.expr(issues_sql(domain, QUARANTINE)))
    if domain != "study":
        # Accepted issues stay auditable in dq_waivers and no longer quarantine the record.
        out = out.join(waived_rules(domain), ["study_id", "submission_id", "usubjid"], "left").withColumn(
            "quarantine_issues",
            F.expr("filter(quarantine_issues, x -> NOT array_contains(coalesce(waived_rules, array()), x.rule_id))"),
        ).drop("waived_rules")
    return (
        out.withColumn("observed_issues", F.expr(issues_sql(domain, OBSERVE)))
        .withColumn("failed_rules", F.expr("transform(quarantine_issues, x -> x.rule_id)"))
        .withColumn("is_record_valid", F.expr("size(quarantine_issues) = 0"))
    )


def with_subjects(df: DataFrame, with_randdt: bool = False) -> DataFrame:
    """Adds `in_dm` (subject exists in demographics) and, for AE, the subject's randomization date."""
    subjects = spark.read.table("dm_subjects").select(
        "study_id", "usubjid", F.lit(True).alias("in_dm"), *(["randdt"] if with_randdt else [])
    )
    return df.join(subjects, ["study_id", "usubjid"], "left").withColumn("in_dm", F.coalesce("in_dm", F.lit(False)))


# ---------------------------------------------------------------------------------------------------------
# Checked tables: every row, with rule failures recorded
# ---------------------------------------------------------------------------------------------------------


@dp.materialized_view(name="silver_study_checked", private=True, comment="All protocol metadata rows with data quality results")
@dp.expect_all(expectations("study"))
def silver_study_checked():
    df = latest("bronze_study_metadata", with_cutoff=False)
    return checked(
        df.select(
            "study_id",
            "submission_id",
            "nct_id",
            "title",
            "phase",
            "indication",
            "therapeutic_area",
            "sponsor",
            F.col("planned_enrollment").cast("int").alias("planned_enrollment"),
            F.col("arms").alias("arms"),
            F.size("sites").alias("planned_sites"),
            F.col("study_start_date").cast("date").alias("study_start_date"),
            F.col("data_cutoff_date").cast("date").alias("data_cutoff_date"),
            "_ingested_at",
        ),
        "study",
    )


@dp.materialized_view(name="silver_dm_checked", private=True, comment="All demographics rows with data quality results")
@dp.expect_all(expectations("dm"))
def silver_dm_checked():
    df = latest("bronze_dm")
    w = Window.partitionBy("study_id", "usubjid")
    out = df.select(
        "study_id",
        "submission_id",
        "data_cutoff_date",
        "_source_file",
        src(df, "SUBJECT_ID").alias("usubjid"),
        src(df, "SITE_ID").alias("siteid"),
        src(df, "ARM").alias("arm"),
        src(df, "SEX").alias("sex"),
        src(df, "AGE").alias("age_raw"),
        src(df, "RACE").alias("race"),
        src(df, "ETHNICITY").alias("ethnic"),
        src(df, "COUNTRY").alias("country"),
        src(df, "CONSENT_DATE").alias("rficdtc_raw"),
        src(df, "RANDOMIZATION_DATE").alias("randdt_raw"),
        src(df, "BMI").alias("bmi_raw"),
    ).selectExpr(
        "*",
        "try_cast(age_raw AS INT) AS age",
        "'YEARS' AS ageu",
        f"{as_date('rficdtc_raw')} AS rficdtc",
        f"{as_date('randdt_raw')} AS randdt",
        "try_cast(bmi_raw AS DOUBLE) AS bmi",
    )
    out = out.withColumn("dup_count", F.when(F.col("usubjid").isNull(), F.lit(1)).otherwise(F.count(F.lit(1)).over(w)))
    return checked(out, "dm")


@dp.temporary_view(name="dm_subjects")
def dm_subjects():
    return (
        spark.read.table("silver_dm_checked")
        .filter("usubjid IS NOT NULL")
        .groupBy("study_id", "usubjid")
        .agg(F.min("randdt").alias("randdt"))
    )


@dp.materialized_view(name="silver_ae_checked", private=True, comment="All adverse event rows with data quality results")
@dp.expect_all(expectations("ae"))
def silver_ae_checked():
    df = latest("bronze_ae")
    out = df.select(
        "study_id",
        "submission_id",
        "data_cutoff_date",
        "_source_file",
        src(df, "SUBJECT_ID").alias("usubjid"),
        src(df, "AE_TERM").alias("aeterm"),
        src(df, "BODY_SYSTEM").alias("aesoc"),
        src(df, "SEVERITY_GRADE").alias("aetoxgr_raw"),
        src(df, "SERIOUS").alias("aeser"),
        src(df, "RELATED").alias("aerel"),
        src(df, "ONSET_DATE").alias("aestdtc_raw"),
        src(df, "END_DATE").alias("aeendtc_raw"),
        src(df, "OUTCOME").alias("aeout"),
        src(df, "ACTION_TAKEN").alias("aeacn"),
    ).selectExpr(
        "*",
        "upper(aeterm) AS aedecod",
        "try_cast(aetoxgr_raw AS INT) AS aetoxgr",
        f"{as_date('aestdtc_raw')} AS aestdtc",
        f"{as_date('aeendtc_raw')} AS aeendtc",
    )
    return checked(with_subjects(out, with_randdt=True), "ae")


@dp.materialized_view(name="silver_vs_checked", private=True, comment="All vital sign rows with data quality results")
@dp.expect_all(expectations("vs"))
def silver_vs_checked():
    df = latest("bronze_vs")
    out = df.select(
        "study_id",
        "submission_id",
        "data_cutoff_date",
        "_source_file",
        src(df, "SUBJECT_ID").alias("usubjid"),
        src(df, "VISIT").alias("visit"),
        src(df, "VISIT_DATE").alias("vsdtc_raw"),
        src(df, "TEST").alias("vstestcd"),
        src(df, "RESULT").alias("vsorres"),
        src(df, "UNIT").alias("vsstresu"),
    ).selectExpr(
        "*",
        f"{visitnum('visit')} AS visitnum",
        f"{as_date('vsdtc_raw')} AS vsdtc",
        "try_cast(vsorres AS DOUBLE) AS vsstresn",
    )
    return checked(with_subjects(out), "vs")


@dp.materialized_view(name="silver_lb_checked", private=True, comment="All central lab rows with data quality results")
@dp.expect_all(expectations("lb"))
def silver_lb_checked():
    df = latest("bronze_lb")
    out = df.select(
        "study_id",
        "submission_id",
        "data_cutoff_date",
        "_source_file",
        src(df, "PATIENT").alias("usubjid"),
        F.upper(src(df, "LAB_TEST")).alias("lbtestcd"),
        src(df, "RESULT_VALUE").alias("lborres"),
        src(df, "UNITS").alias("lbstresu"),
        src(df, "REF_LOW").alias("lbornrlo_raw"),
        src(df, "REF_HIGH").alias("lbornrhi_raw"),
        src(df, "COLLECTION_DATE").alias("lbdtc_raw"),
        src(df, "VISIT").alias("visit"),
    ).selectExpr(
        "*",
        "try_cast(lborres AS DOUBLE) AS lbstresn",
        "try_cast(lbornrlo_raw AS DOUBLE) AS lbornrlo",
        "try_cast(lbornrhi_raw AS DOUBLE) AS lbornrhi",
        f"{as_date('lbdtc_raw')} AS lbdtc",
        f"{visitnum('visit')} AS visitnum",
    )
    out = out.withColumn(
        "lbnrind",
        F.expr(
            """CASE WHEN lbstresn IS NULL THEN NULL
                    WHEN lbornrlo IS NULL OR lbornrhi IS NULL THEN 'UNKNOWN'
                    WHEN lbstresn < lbornrlo THEN 'LOW'
                    WHEN lbstresn > lbornrhi THEN 'HIGH'
                    ELSE 'NORMAL' END"""
        ),
    )
    unit_rank = Window.partitionBy("study_id", "lbtestcd").orderBy(F.col("n").desc(), F.col("lbstresu"))
    study_units = (
        out.filter("lbstresu IS NOT NULL")
        .groupBy("study_id", "lbtestcd", "lbstresu")
        .agg(F.count(F.lit(1)).alias("n"))
        .withColumn("_rn", F.row_number().over(unit_rank))
        .filter("_rn = 1")
        .select("study_id", "lbtestcd", F.col("lbstresu").alias("study_unit"))
    )
    return checked(with_subjects(out.join(study_units, ["study_id", "lbtestcd"], "left")), "lb")


@dp.materialized_view(name="silver_ex_checked", private=True, comment="All exposure rows with data quality results")
@dp.expect_all(expectations("ex"))
def silver_ex_checked():
    df = latest("bronze_ex")
    out = df.select(
        "study_id",
        "submission_id",
        "data_cutoff_date",
        "_source_file",
        src(df, "SUBJECT_ID").alias("usubjid"),
        src(df, "TREATMENT").alias("extrt"),
        src(df, "DOSE").alias("exdose_raw"),
        src(df, "DOSE_UNIT").alias("exdosu"),
        src(df, "START_DATE").alias("exstdtc_raw"),
        src(df, "END_DATE").alias("exendtc_raw"),
    ).selectExpr(
        "*",
        "try_cast(exdose_raw AS DOUBLE) AS exdose",
        f"{as_date('exstdtc_raw')} AS exstdtc",
        f"{as_date('exendtc_raw')} AS exendtc",
    )
    return checked(with_subjects(out), "ex")


@dp.materialized_view(name="silver_ds_checked", private=True, comment="All disposition rows with data quality results")
@dp.expect_all(expectations("ds"))
def silver_ds_checked():
    df = latest("bronze_ds")
    out = df.select(
        "study_id",
        "submission_id",
        "data_cutoff_date",
        "_source_file",
        src(df, "SUBJECT_ID").alias("usubjid"),
        src(df, "STATUS").alias("dsdecod"),
        src(df, "REASON").alias("dsterm"),
        src(df, "DISPOSITION_DATE").alias("dsstdtc_raw"),
    ).selectExpr("*", f"{as_date('dsstdtc_raw')} AS dsstdtc")
    return checked(with_subjects(out), "ds")


@dp.materialized_view(name="silver_sv_checked", private=True, comment="All subject visit rows with data quality results")
@dp.expect_all(expectations("sv"))
def silver_sv_checked():
    df = latest("bronze_sv")
    out = df.select(
        "study_id",
        "submission_id",
        "data_cutoff_date",
        "_source_file",
        src(df, "SUBJECT_ID").alias("usubjid"),
        src(df, "VISIT").alias("visit"),
        src(df, "PLANNED_DATE").alias("svpldtc_raw"),
        src(df, "ACTUAL_DATE").alias("svstdtc_raw"),
    ).selectExpr(
        "*",
        f"{visitnum('visit')} AS visitnum",
        f"{as_date('svpldtc_raw')} AS svpldtc",
        f"{as_date('svstdtc_raw')} AS svstdtc",
    )
    out = out.withColumn("days_from_planned", F.datediff("svstdtc", "svpldtc"))
    return checked(with_subjects(out), "sv")


# ---------------------------------------------------------------------------------------------------------
# Subject status: a subject is clean only when no record in any domain failed a quarantine rule
# ---------------------------------------------------------------------------------------------------------


@dp.materialized_view(
    name="silver_subject_status",
    comment="One row per subject in demographics: quarantined record counts per domain, failed rules and is_clean",
    table_properties={"quality": "silver"},
)
def silver_subject_status():
    subjects = (
        spark.read.table("silver_dm_checked")
        .filter("usubjid IS NOT NULL")
        .groupBy("study_id", "usubjid")
        .agg(F.first("siteid", ignorenulls=True).alias("site_id"), F.first("country", ignorenulls=True).alias("country"))
    )
    counts, rules = [], []
    for d in SUBJECT_DOMAINS:
        agg = (
            spark.read.table(f"silver_{d}_checked")
            .filter("usubjid IS NOT NULL")
            .groupBy("study_id", "usubjid")
            .agg(
                F.sum(F.when(F.col("is_record_valid"), 0).otherwise(1)).alias(f"{d}_quarantined"),
                F.array_distinct(F.flatten(F.collect_list("failed_rules"))).alias(f"{d}_rules"),
            )
        )
        subjects = subjects.join(agg, ["study_id", "usubjid"], "left")
        counts.append(F.coalesce(F.col(f"{d}_quarantined"), F.lit(0)))
        rules.append(F.expr(f"transform(coalesce({d}_rules, array()), x -> concat('{d.upper()}.', x))"))
    total = counts[0]
    for c in counts[1:]:
        total = total + c
    return (
        subjects.withColumn("records_quarantined", total)
        .withColumn("failed_rules", F.array_distinct(F.flatten(F.array(*rules))))
        .withColumn("is_clean", F.col("records_quarantined") == 0)
        .drop(*[f"{d}_rules" for d in SUBJECT_DOMAINS])
        .na.fill(0, [f"{d}_quarantined" for d in SUBJECT_DOMAINS])
    )


# ---------------------------------------------------------------------------------------------------------
# Clean and quarantine outputs
# ---------------------------------------------------------------------------------------------------------


def with_status(domain: str) -> DataFrame:
    df = spark.read.table(f"silver_{domain}_checked")
    if domain == "study":
        return df.withColumn("is_clean", F.lit(True))
    status = spark.read.table("silver_subject_status").select("study_id", "usubjid", "is_clean")
    return df.join(status, ["study_id", "usubjid"], "left").withColumn("is_clean", F.coalesce("is_clean", F.lit(False)))


def define_outputs(domain: str) -> None:
    description = DESCRIPTIONS[domain]

    @dp.materialized_view(
        name=f"silver_{domain}",
        comment=f"Clean {description}. Valid records of clean subjects only; everything else is in silver_{domain}_quarantine",
        table_properties={"quality": "silver"},
    )
    def clean():
        df = with_status(domain).filter("is_record_valid AND is_clean")
        drop = [c for c in df.columns if c.endswith("_raw")] + HELPERS[domain] + CHECK_COLUMNS + ["is_clean", "_source_file"]
        return df.drop(*drop)

    @dp.materialized_view(
        name=f"silver_{domain}_quarantine",
        comment=(
            f"Quarantined {description}: records that failed a data quality rule, plus every record of a "
            "flagged subject (SUBJECT_CASCADE). Never shown to Genie or the AI insights"
        ),
        table_properties={"quality": "quarantine"},
    )
    def quarantine():
        return (
            with_status(domain)
            .filter("NOT (is_record_valid AND is_clean)")
            .withColumn(
                "quarantine_reason",
                F.expr("CASE WHEN size(failed_rules) > 0 THEN array_join(failed_rules, ', ') ELSE 'SUBJECT_CASCADE' END"),
            )
            .drop("observed_issues", "is_record_valid")
        )


for _domain in ["study", *SUBJECT_DOMAINS]:
    define_outputs(_domain)
