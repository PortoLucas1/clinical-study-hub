"""Bronze: incremental ingestion of staged study files with Auto Loader.

Files land in raw/<study_id>/<domain>/<submission_id>__<file>.csv. Every column is
kept as a string and new columns are added automatically (schema evolution), so a
sponsor adding a field to an EDC export never breaks ingestion.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

RAW_PATH = spark.conf.get("raw_path")

DOMAINS = {
    "dm": "Demographics (EDC)",
    "ae": "Adverse events (EDC)",
    "vs": "Vital signs (EDC)",
    "ex": "Study drug exposure (EDC)",
    "ds": "Subject disposition (EDC)",
    "sv": "Subject visits (EDC)",
    "lb": "Central laboratory results (vendor Excel, converted to CSV at staging)",
}


def with_lineage(df):
    path = F.col("_metadata.file_path")
    return (
        df.withColumn("study_id", F.regexp_extract(path, r"/raw/([^/]+)/", 1))
        .withColumn("submission_id", F.regexp_extract(path, r"/([^/]+)__[^/]+$", 1))
        .withColumn("_source_file", path)
        .withColumn("_ingested_at", F.current_timestamp())
    )


def define_bronze(domain: str, description: str) -> None:
    @dp.table(
        name=f"bronze_{domain}",
        comment=f"Bronze {description}: raw rows as received, all strings, with file lineage",
        table_properties={"quality": "bronze"},
    )
    def bronze():
        return with_lineage(
            spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "csv")
            .option("header", "true")
            .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
            .load(f"{RAW_PATH}/*/{domain}/")
        )


for _domain, _description in DOMAINS.items():
    define_bronze(_domain, _description)


@dp.table(
    name="bronze_study_metadata",
    comment="Bronze protocol metadata (study_metadata.json) for each staged package",
    table_properties={"quality": "bronze"},
)
def bronze_study_metadata():
    return with_lineage(
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
        .load(f"{RAW_PATH}/*/meta/")
    )
