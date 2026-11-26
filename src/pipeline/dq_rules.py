"""Data quality rules registry: the single source of truth for every check in the pipeline.

Each rule states the condition a VALID record meets. Rules tagged `quarantine` send the record (and every
record of its subject) to the quarantine tables; rules tagged `observe` describe real data worth reporting,
such as protocol deviations, and never remove a record from the clean tables. The Silver checked tables
apply these rules as expectations (metrics in the event log), the Gold data quality tables are generated
from them, and `dq_rules` publishes them so the app can explain each rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

QUARANTINE = "quarantine"
OBSERVE = "observe"

ISSUE_TYPE = "ARRAY<STRUCT<rule_id: STRING, detail: STRING>>"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    domain: str
    severity: str
    action: str
    description: str
    valid: str
    detail: str


def _subject_rules(domain: str) -> list[Rule]:
    return [
        Rule("KEY01", domain, "High", QUARANTINE, "Subject ID missing",
             "usubjid IS NOT NULL AND trim(usubjid) <> ''", "'Row has no subject ID'"),
        Rule("REF01", domain, "High", QUARANTINE, "Subject not found in demographics",
             "in_dm", "concat('USUBJID=', coalesce(usubjid, 'missing'), ' has no demographics record')"),
    ]


def _parsed(*cols: str) -> str:
    return " AND ".join(f"({c}_raw IS NULL OR {c} IS NOT NULL)" for c in cols)


def _raw_detail(*cols: str) -> str:
    parts = ", ' ', ".join(f"'{c.upper()}=', coalesce({c}_raw, '')" for c in cols)
    return f"concat({parts})"


def _not_after_cutoff(col: str) -> str:
    return f"{col} IS NULL OR data_cutoff_date IS NULL OR {col} <= data_cutoff_date"


VITALS_PLAUSIBLE = """CASE vstestcd
  WHEN 'SYSBP' THEN vsstresn BETWEEN 60 AND 250
  WHEN 'DIABP' THEN vsstresn BETWEEN 30 AND 150
  WHEN 'HR' THEN vsstresn BETWEEN 30 AND 220
  WHEN 'TEMP' THEN vsstresn BETWEEN 33 AND 42
  WHEN 'WEIGHT' THEN vsstresn BETWEEN 25 AND 300
  ELSE TRUE END"""

RULES: list[Rule] = [
    Rule("ST01", "study", "High", QUARANTINE, "Study ID missing in protocol metadata",
         "study_id IS NOT NULL AND trim(study_id) <> ''", "'study_metadata.json has no study_id'"),
    # Demographics
    Rule("KEY01", "dm", "High", QUARANTINE, "Subject ID missing",
         "usubjid IS NOT NULL AND trim(usubjid) <> ''", "'Row has no subject ID'"),
    Rule("KEY02", "dm", "High", QUARANTINE, "Duplicate subject in demographics",
         "dup_count = 1", "concat(usubjid, ' appears ', dup_count, ' times')"),
    Rule("DM01", "dm", "High", QUARANTINE, "Age outside protocol range (18-100) or missing",
         "age BETWEEN 18 AND 100", "concat('AGE=', coalesce(age_raw, 'missing'))"),
    Rule("DM02", "dm", "High", QUARANTINE, "Informed consent date missing",
         "rficdtc_raw IS NOT NULL", "'RFICDTC is missing'"),
    Rule("DM03", "dm", "Medium", QUARANTINE, "Treatment arm missing",
         "arm IS NOT NULL AND trim(arm) <> ''", "'ARM is missing'"),
    Rule("DT01", "dm", "Medium", QUARANTINE, "Date could not be parsed",
         _parsed("rficdtc", "randdt"), _raw_detail("rficdtc", "randdt")),
    # Adverse events
    *_subject_rules("ae"),
    Rule("AE01", "ae", "Medium", QUARANTINE, "AE end date before onset date",
         "aeendtc IS NULL OR aestdtc IS NULL OR aeendtc >= aestdtc",
         "concat(coalesce(aeterm, ''), ': onset ', coalesce(cast(aestdtc AS STRING), ''), ', end ', coalesce(cast(aeendtc AS STRING), ''))"),
    Rule("AE03", "ae", "Medium", QUARANTINE, "AE toxicity grade missing or outside 1-5",
         "aetoxgr BETWEEN 1 AND 5", "concat(coalesce(aeterm, ''), ': GRADE=', coalesce(aetoxgr_raw, 'missing'))"),
    Rule("AE04", "ae", "Medium", QUARANTINE, "AE onset date missing",
         "aestdtc_raw IS NOT NULL", "concat(coalesce(aeterm, ''), ': onset date missing')"),
    Rule("DT01", "ae", "Medium", QUARANTINE, "Date could not be parsed",
         _parsed("aestdtc", "aeendtc"), _raw_detail("aestdtc", "aeendtc")),
    Rule("DT02", "ae", "Medium", QUARANTINE, "AE onset after the data cutoff date",
         _not_after_cutoff("aestdtc"), "concat('onset ', cast(aestdtc AS STRING), ' > cutoff ', cast(data_cutoff_date AS STRING))"),
    Rule("AE02", "ae", "Low", OBSERVE, "AE onset before randomization",
         "randdt IS NULL OR aestdtc IS NULL OR aestdtc >= randdt",
         "concat(coalesce(aeterm, ''), ': onset ', cast(aestdtc AS STRING), ', randomized ', cast(randdt AS STRING))"),
    # Vital signs
    *_subject_rules("vs"),
    Rule("VS01", "vs", "High", QUARANTINE, "Vital sign physiologically implausible",
         f"vsstresn IS NULL OR ({VITALS_PLAUSIBLE})",
         "concat(vstestcd, '=', coalesce(vsorres, ''), ' ', coalesce(vsstresu, ''), ' at ', coalesce(visit, ''))"),
    Rule("VS02", "vs", "Medium", QUARANTINE, "Vital sign result not numeric or missing",
         "vsstresn IS NOT NULL", "concat(vstestcd, ' at ', coalesce(visit, ''), ': \"', coalesce(vsorres, ''), '\"')"),
    Rule("DT01", "vs", "Medium", QUARANTINE, "Date could not be parsed", _parsed("vsdtc"), _raw_detail("vsdtc")),
    Rule("DT02", "vs", "Medium", QUARANTINE, "Measurement after the data cutoff date",
         _not_after_cutoff("vsdtc"), "concat('visit ', cast(vsdtc AS STRING), ' > cutoff ', cast(data_cutoff_date AS STRING))"),
    # Central lab
    *_subject_rules("lb"),
    Rule("LB01", "lb", "Medium", QUARANTINE, "Lab result not numeric or missing",
         "lbstresn IS NOT NULL", "concat(lbtestcd, ' at ', coalesce(visit, ''), ': \"', coalesce(lborres, ''), '\"')"),
    Rule("LB02", "lb", "Medium", QUARANTINE, "Lab reference range missing",
         "lbornrlo IS NOT NULL AND lbornrhi IS NOT NULL",
         "concat(lbtestcd, ' at ', coalesce(visit, ''), ': REF_LOW=', coalesce(lbornrlo_raw, ''), ' REF_HIGH=', coalesce(lbornrhi_raw, ''))"),
    Rule("LB03", "lb", "Medium", QUARANTINE, "Lab unit differs from the study unit for this test",
         "lbstresu <=> study_unit", "concat(lbtestcd, ': unit ', coalesce(lbstresu, 'missing'), ', study unit ', coalesce(study_unit, 'missing'))"),
    Rule("DT01", "lb", "Medium", QUARANTINE, "Date could not be parsed", _parsed("lbdtc"), _raw_detail("lbdtc")),
    Rule("DT02", "lb", "Medium", QUARANTINE, "Collection after the data cutoff date",
         _not_after_cutoff("lbdtc"), "concat('collected ', cast(lbdtc AS STRING), ' > cutoff ', cast(data_cutoff_date AS STRING))"),
    # Exposure
    *_subject_rules("ex"),
    Rule("DT01", "ex", "Medium", QUARANTINE, "Date could not be parsed",
         _parsed("exstdtc", "exendtc"), _raw_detail("exstdtc", "exendtc")),
    # Disposition
    *_subject_rules("ds"),
    Rule("DS01", "ds", "Medium", QUARANTINE, "Discontinuation without a reason",
         "dsdecod <> 'DISCONTINUED' OR dsterm IS NOT NULL", "concat('STATUS=', coalesce(dsdecod, ''), ', REASON missing')"),
    Rule("DT01", "ds", "Medium", QUARANTINE, "Date could not be parsed", _parsed("dsstdtc"), _raw_detail("dsstdtc")),
    # Subject visits
    *_subject_rules("sv"),
    Rule("DT01", "sv", "Medium", QUARANTINE, "Date could not be parsed",
         _parsed("svpldtc", "svstdtc"), _raw_detail("svpldtc", "svstdtc")),
    Rule("DT02", "sv", "Medium", QUARANTINE, "Visit after the data cutoff date",
         _not_after_cutoff("svstdtc"), "concat(coalesce(visit, ''), ' on ', cast(svstdtc AS STRING), ' > cutoff ', cast(data_cutoff_date AS STRING))"),
    Rule("SV01", "sv", "Low", OBSERVE, "Visit outside protocol window (+/- 7 days)",
         "days_from_planned IS NULL OR abs(days_from_planned) <= 7",
         "concat(coalesce(visit, ''), ': ', days_from_planned, ' days from planned')"),
]

SUBJECT_DOMAINS = ["dm", "ae", "vs", "lb", "ex", "ds", "sv"]


def rules_for(domain: str, action: str | None = None) -> list[Rule]:
    return [r for r in RULES if r.domain == domain and (action is None or r.action == action)]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def expectations(domain: str) -> dict[str, str]:
    """Every rule of the domain as a warn-only expectation: metrics are recorded, no row is dropped."""
    return {f"{r.rule_id}_{_slug(r.description)}": f"coalesce(({r.valid}), false)" for r in rules_for(domain)}


def issues_sql(domain: str, action: str) -> str:
    """SQL expression that returns the rule failures of one record as an array of (rule_id, detail)."""
    rules = rules_for(domain, action)
    if not rules:
        return f"CAST(array() AS {ISSUE_TYPE})"
    cases = ",\n  ".join(
        f"CASE WHEN NOT coalesce(({r.valid}), false) "
        f"THEN named_struct('rule_id', '{r.rule_id}', 'detail', CAST(({r.detail}) AS STRING)) END"
        for r in rules
    )
    return f"CAST(filter(array(\n  {cases}\n), x -> x IS NOT NULL) AS {ISSUE_TYPE})"


def rules_rows() -> list[tuple[str, str, str, str, str, str]]:
    return [(r.rule_id, r.domain.upper(), r.severity, r.action, r.description, r.valid) for r in RULES]
