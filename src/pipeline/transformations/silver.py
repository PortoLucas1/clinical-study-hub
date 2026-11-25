"""Silver: standardized, SDTM-like study domains.

Raw EDC and vendor column names are mapped to SDTM-style variables (USUBJID, AETERM,
LBTESTCD, ...), values are typed, and data quality expectations (the data
quality layer) are evaluated. Only the latest approved submission of each study is
kept, so re-submitting a study package replaces its previous version.
"""

from pyspark import pipelines as dp
from pyspark.sql import Window
from pyspark.sql import functions as F

VISIT_ORDER = {"SCREENING": 0, "BASELINE": 1, "WEEK 4": 2, "WEEK 8": 3, "WEEK 12": 4, "WEEK 24": 5}


def latest_submission(table: str):
    df = spark.read.table(table)
    w = Window.partitionBy("study_id")
    return df.withColumn("_latest", F.max("submission_id").over(w)).filter("submission_id = _latest").drop("_latest")


def as_date(col: str):
    return F.expr(f"try_cast(substr(nullif(trim({col}), ''), 1, 10) AS DATE)")


def as_double(col: str):
    return F.expr(f"try_cast(nullif(trim({col}), '') AS DOUBLE)")


def optional(df, col: str, dtype: str = "string"):
    return F.col(col).cast(dtype) if col in df.columns else F.lit(None).cast(dtype)


def visitnum(col: str):
    expr = "CASE " + " ".join(f"WHEN upper({col}) = '{k}' THEN {v}" for k, v in VISIT_ORDER.items()) + " END"
    return F.expr(expr)


@dp.materialized_view(
    name="silver_study",
    comment="Study protocol metadata: one row per study (latest approved package)",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("valid_study_id", "study_id IS NOT NULL AND study_id <> ''")
def silver_study():
    df = latest_submission("bronze_study_metadata")
    return df.select(
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
    )


@dp.materialized_view(
    name="silver_dm",
    comment="SDTM-like DM (Demographics): one row per subject",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("valid_usubjid", "usubjid IS NOT NULL AND usubjid <> ''")
@dp.expect("age_in_protocol_range", "age BETWEEN 18 AND 100")
@dp.expect("consent_date_present", "rficdtc IS NOT NULL")
@dp.expect("arm_assigned", "arm IS NOT NULL")
def silver_dm():
    df = latest_submission("bronze_dm")
    return df.select(
        "study_id",
        "submission_id",
        F.col("SUBJECT_ID").alias("usubjid"),
        F.col("SITE_ID").alias("siteid"),
        F.col("ARM").alias("arm"),
        F.col("SEX").alias("sex"),
        F.expr("try_cast(AGE AS INT)").alias("age"),
        F.lit("YEARS").alias("ageu"),
        F.col("RACE").alias("race"),
        F.col("ETHNICITY").alias("ethnic"),
        F.col("COUNTRY").alias("country"),
        as_date("CONSENT_DATE").alias("rficdtc"),
        as_date("RANDOMIZATION_DATE").alias("randdt"),
        optional(df, "BMI", "double").alias("bmi"),
    )


@dp.materialized_view(
    name="silver_ae",
    comment="SDTM-like AE (Adverse Events): one row per reported event",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("valid_usubjid", "usubjid IS NOT NULL")
@dp.expect("valid_toxicity_grade", "aetoxgr BETWEEN 1 AND 5")
@dp.expect("end_on_or_after_onset", "aeendtc IS NULL OR aeendtc >= aestdtc")
def silver_ae():
    df = latest_submission("bronze_ae")
    return df.select(
        "study_id",
        "submission_id",
        F.col("SUBJECT_ID").alias("usubjid"),
        F.col("AE_TERM").alias("aeterm"),
        F.upper("AE_TERM").alias("aedecod"),
        F.col("BODY_SYSTEM").alias("aesoc"),
        F.expr("try_cast(SEVERITY_GRADE AS INT)").alias("aetoxgr"),
        F.col("SERIOUS").alias("aeser"),
        F.col("RELATED").alias("aerel"),
        as_date("ONSET_DATE").alias("aestdtc"),
        as_date("END_DATE").alias("aeendtc"),
        F.col("OUTCOME").alias("aeout"),
        optional(df, "ACTION_TAKEN").alias("aeacn"),
    )


@dp.materialized_view(
    name="silver_vs",
    comment="SDTM-like VS (Vital Signs): one row per measurement",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("valid_usubjid", "usubjid IS NOT NULL")
@dp.expect(
    "physiologically_plausible",
    """CASE vstestcd
         WHEN 'SYSBP' THEN vsstresn BETWEEN 60 AND 250
         WHEN 'DIABP' THEN vsstresn BETWEEN 30 AND 150
         WHEN 'HR' THEN vsstresn BETWEEN 30 AND 220
         WHEN 'TEMP' THEN vsstresn BETWEEN 33 AND 42
         WHEN 'WEIGHT' THEN vsstresn BETWEEN 25 AND 300
         ELSE TRUE END""",
)
def silver_vs():
    df = latest_submission("bronze_vs")
    return df.select(
        "study_id",
        "submission_id",
        F.col("SUBJECT_ID").alias("usubjid"),
        F.col("VISIT").alias("visit"),
        visitnum("VISIT").alias("visitnum"),
        as_date("VISIT_DATE").alias("vsdtc"),
        F.col("TEST").alias("vstestcd"),
        F.col("RESULT").alias("vsorres"),
        as_double("RESULT").alias("vsstresn"),
        F.col("UNIT").alias("vsstresu"),
    )


@dp.materialized_view(
    name="silver_lb",
    comment="SDTM-like LB (Laboratory): central lab vendor results mapped to SDTM variables",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("valid_usubjid", "usubjid IS NOT NULL")
@dp.expect("numeric_result", "lbstresn IS NOT NULL")
def silver_lb():
    df = latest_submission("bronze_lb")
    lo, hi, val = as_double("REF_LOW"), as_double("REF_HIGH"), as_double("RESULT_VALUE")
    return df.select(
        "study_id",
        "submission_id",
        F.col("PATIENT").alias("usubjid"),
        F.upper("LAB_TEST").alias("lbtestcd"),
        F.col("RESULT_VALUE").alias("lborres"),
        val.alias("lbstresn"),
        F.col("UNITS").alias("lbstresu"),
        lo.alias("lbornrlo"),
        hi.alias("lbornrhi"),
        F.when(val.isNull(), None).when(val < lo, "LOW").when(val > hi, "HIGH").otherwise("NORMAL").alias("lbnrind"),
        as_date("COLLECTION_DATE").alias("lbdtc"),
        F.col("VISIT").alias("visit"),
        visitnum("VISIT").alias("visitnum"),
    )


@dp.materialized_view(
    name="silver_ex",
    comment="SDTM-like EX (Exposure): study treatment administration per subject",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("valid_usubjid", "usubjid IS NOT NULL")
def silver_ex():
    df = latest_submission("bronze_ex")
    return df.select(
        "study_id",
        "submission_id",
        F.col("SUBJECT_ID").alias("usubjid"),
        F.col("TREATMENT").alias("extrt"),
        as_double("DOSE").alias("exdose"),
        F.col("DOSE_UNIT").alias("exdosu"),
        as_date("START_DATE").alias("exstdtc"),
        as_date("END_DATE").alias("exendtc"),
    )


@dp.materialized_view(
    name="silver_ds",
    comment="SDTM-like DS (Disposition): current status per subject",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("valid_usubjid", "usubjid IS NOT NULL")
@dp.expect("discontinuation_has_reason", "dsdecod <> 'DISCONTINUED' OR (dsterm IS NOT NULL AND dsterm <> '')")
def silver_ds():
    df = latest_submission("bronze_ds")
    return df.select(
        "study_id",
        "submission_id",
        F.col("SUBJECT_ID").alias("usubjid"),
        F.col("STATUS").alias("dsdecod"),
        F.nullif(F.trim("REASON"), F.lit("")).alias("dsterm"),
        as_date("DISPOSITION_DATE").alias("dsstdtc"),
    )


@dp.materialized_view(
    name="silver_sv",
    comment="SDTM-like SV (Subject Visits): planned vs actual visit dates with visit window compliance",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("valid_usubjid", "usubjid IS NOT NULL")
@dp.expect("visit_within_window", "abs(days_from_planned) <= 7")
def silver_sv():
    df = latest_submission("bronze_sv")
    return df.select(
        "study_id",
        "submission_id",
        F.col("SUBJECT_ID").alias("usubjid"),
        F.col("VISIT").alias("visit"),
        visitnum("VISIT").alias("visitnum"),
        as_date("PLANNED_DATE").alias("svpldtc"),
        as_date("ACTUAL_DATE").alias("svstdtc"),
    ).withColumn("days_from_planned", F.datediff("svstdtc", "svpldtc"))
