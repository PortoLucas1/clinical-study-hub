"""Create (or update) the Study Insights Genie space over the clean study tables.

Only clean data is exposed: the Gold marts and the clean Silver tables cover clean subjects, and data quality
is exposed as counts (gold_dq_summary). Quarantine tables, gold_dq_issues (its details contain the offending
values) and the AI briefing (model text) are deliberately left out. scripts/genie_eval.py checks the answers.

Usage:
    python3 scripts/create_genie_space.py                 # create, prints the space id
    GENIE_SPACE_ID=<id> python3 scripts/create_genie_space.py   # update in place
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid

PROFILE = os.environ.get("PROFILE", "")
WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "")
FQ = f"{os.environ.get('CATALOG', 'clinical_demo')}.{os.environ.get('SCHEMA', 'study_onboarding')}"
SPACE_ID = os.environ.get("GENIE_SPACE_ID", "")


def newid() -> str:
    return uuid.uuid4().hex


TABLES = [
    "gold_study_overview",
    "gold_patient_profile",
    "gold_ae_summary",
    "gold_ae_by_arm",
    "gold_lab_abnormalities",
    "gold_vitals_trends",
    "gold_enrollment_by_month",
    "gold_site_performance",
    "gold_dq_summary",
    "silver_ae",
    "silver_lb",
]

CATEGORICAL = {
    "gold_patient_profile": ["arm", "country", "disposition_status", "discontinuation_reason", "sex", "site_id", "study_id"],
    "gold_ae_summary": ["arm", "preferred_term", "study_id", "system_organ_class"],
    "gold_ae_by_arm": ["arm", "study_id"],
    "gold_lab_abnormalities": ["arm", "lab_test", "study_id", "visit"],
    "gold_vitals_trends": ["arm", "study_id", "visit", "vital_test"],
    "gold_site_performance": ["country", "site_id", "study_id"],
    "gold_dq_summary": ["action", "domain", "rule_id", "severity", "study_id"],
    "gold_study_overview": ["phase", "study_id", "therapeutic_area"],
    "silver_ae": ["aedecod", "aeout", "aesoc", "study_id"],
    "silver_lb": ["lbnrind", "lbtestcd", "study_id", "visit"],
}

INSTRUCTIONS = [
    "You are the Study Insights assistant for clinical study teams (medical monitors, clinical operations, data managers). All data is synthetic.",
    "Every table has a study_id column (e.g. 'ONC-101', 'CARD-202', 'RESP-303'). When the user's question starts with a context like [Study: ONC-101], ALWAYS filter every query with study_id = 'ONC-101'. If no study is given and the question is study-specific, ask which study, or break results down by study_id.",
    "Data scope: every table in this space holds validated data for CLEAN subjects only. Records that failed a data quality rule, and all records of the affected subjects, are quarantined for data management review and are not available here. Never claim to see quarantined data; if asked for it, explain it is reviewed in the Study Hub app.",
    "Coverage: when you report a count, rate or list of subjects for a study, also state the coverage from gold_study_overview, for example 'based on 72 of 88 subjects (16 quarantined)', using subjects_clean, subjects_received and subjects_quarantined.",
    "Study-level KPIs (enrollment vs plan, disposition, SAE rate, data quality totals and coverage) live in gold_study_overview. Subject-level detail lives in gold_patient_profile (one row per clean subject, column usubjid).",
    "Safety: use gold_ae_by_arm for rates per arm (pct_with_ae, pct_with_sae, pct_grade3plus). Use gold_ae_summary for system organ class / preferred term breakdowns. SAE means serious adverse event (aeser = 'Y' in silver_ae). Grade 3+ means aetoxgr >= 3 (CTCAE toxicity grade).",
    "Labs: gold_lab_abnormalities has abnormal rates (pct_abnormal = HIGH or LOW vs reference range) per arm, lab_test and visit. 'Post-baseline' means visitnum >= 2. Visit order: SCREENING=0, BASELINE=1, WEEK 4=2, WEEK 8=3, WEEK 12=4, WEEK 24=5. Always order visits by visitnum, not alphabetically.",
    "Data quality (automated rules): gold_dq_summary has issue counts per study, domain and rule (rule_id, rule_description, severity, action, issue_count, subjects_affected). action = 'quarantine' means the records were moved to quarantine; action = 'observe' means real data that is kept and reported, such as out-of-window visits (SV01) or AEs before randomization (AE02). Report counts only.",
    "Operations: gold_site_performance has per-site enrollment, discontinuation rate, SAEs, visit compliance, DQ issue counts and quarantined subjects. gold_enrollment_by_month has monthly and cumulative enrollment per arm.",
    "The AI briefing is not in this space. If asked for the study summary or briefing, say it is on the study page of the Study Hub app.",
    "Round percentages to 1 decimal. When comparing arms, show both arms side by side.",
]

EXAMPLES = [
    (
        "What is the SAE rate by treatment arm?",
        f"SELECT study_id, arm, subjects_in_arm, subjects_with_sae, pct_with_sae FROM {FQ}.gold_ae_by_arm ORDER BY study_id, arm",
    ),
    (
        "Which sites have the most data quality issues?",
        f"SELECT study_id, site_id, country, dq_issues, subjects_quarantined, subjects_received, pct_visits_out_of_window FROM {FQ}.gold_site_performance ORDER BY dq_issues DESC LIMIT 10",
    ),
    (
        "How many subjects are enrolled in each study?",
        f"SELECT study_id, enrolled, planned_enrollment, pct_enrollment_target, subjects_received, subjects_quarantined FROM {FQ}.gold_study_overview ORDER BY study_id",
    ),
    (
        "How many subjects are clean and how many are quarantined?",
        f"SELECT study_id, subjects_received, subjects_clean, subjects_quarantined, pct_subjects_clean FROM {FQ}.gold_study_overview ORDER BY study_id",
    ),
    (
        "How many data quality issues are there by rule?",
        f"SELECT study_id, domain, rule_id, rule_description, action, issue_count, subjects_affected FROM {FQ}.gold_dq_summary ORDER BY study_id, issue_count DESC",
    ),
    (
        "Show the ALT trend by visit and arm",
        f"SELECT study_id, arm, visit, visitnum, mean_value, pct_abnormal FROM {FQ}.gold_lab_abnormalities WHERE lab_test = 'ALT' ORDER BY study_id, arm, visitnum",
    ),
    (
        "Top 10 adverse events by number of subjects",
        f"SELECT study_id, preferred_term, system_organ_class, SUM(subjects) AS subjects, SUM(events) AS events, SUM(serious_events) AS serious_events FROM {FQ}.gold_ae_summary GROUP BY ALL ORDER BY subjects DESC LIMIT 10",
    ),
]

SAMPLE_QUESTIONS = [
    "What is the SAE rate by treatment arm?",
    "Which adverse events are more frequent in the investigational arm?",
    "Show the ALT trend by visit for each arm",
    "Which sites have the highest discontinuation rate?",
    "List subjects with grade 3 or higher adverse events",
    "How many subjects are clean and how many are quarantined?",
]


def build() -> str:
    tables = []
    for t in sorted(TABLES):
        entry: dict = {"identifier": f"{FQ}.{t}"}
        cols = CATEGORICAL.get(t)
        if cols:
            entry["column_configs"] = [
                {"column_name": c, "enable_format_assistance": True, "enable_entity_matching": True} for c in sorted(cols)
            ]
        tables.append(entry)
    payload = {
        "version": 2,
        "config": {"sample_questions": sorted([{"id": newid(), "question": [q]} for q in SAMPLE_QUESTIONS], key=lambda x: x["id"])},
        "data_sources": {"tables": tables},
        "instructions": {
            "text_instructions": [{"id": newid(), "content": ["\n".join(INSTRUCTIONS)]}],
            "example_question_sqls": sorted(
                [{"id": newid(), "question": [q], "sql": [s]} for q, s in EXAMPLES], key=lambda x: x["id"]
            ),
        },
    }
    return json.dumps(payload)


def _cli(args: list[str]) -> subprocess.CompletedProcess:
    cmd = ["databricks", *args]
    if PROFILE:
        cmd += ["--profile", PROFILE]
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def existing_space_id(title: str) -> str:
    r = _cli(["genie", "list-spaces", "-o", "json"])
    if r.returncode != 0:
        return ""
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return ""
    for space in data.get("spaces") or []:
        if (space.get("title") or space.get("name")) == title:
            return str(space.get("space_id") or space.get("id") or "")
    return ""


def main() -> None:
    serialized = build()
    title = os.environ.get("GENIE_TITLE", "Study Insights")
    description = "Ask questions about onboarded clinical studies: enrollment, safety, labs, sites and data quality (synthetic data)."
    space_id = SPACE_ID or existing_space_id(title)
    if space_id:
        body = json.dumps({"serialized_space": serialized, "title": title, "description": description})
        r = _cli(["genie", "update-space", space_id, "--json", body, "-o", "json"])
        if r.returncode != 0:
            raise SystemExit(r.stderr or r.stdout or "genie update-space failed")
        print(space_id)
        return
    if not WAREHOUSE_ID:
        raise SystemExit("Set WAREHOUSE_ID (and optional PROFILE or DATABRICKS_HOST+TOKEN)")
    r = _cli(
        [
            "genie",
            "create-space",
            WAREHOUSE_ID,
            serialized,
            "--title",
            title,
            "--description",
            description,
            "-o",
            "json",
        ]
    )
    if r.returncode != 0:
        raise SystemExit(r.stderr or r.stdout or "genie create-space failed")
    space = json.loads(r.stdout)
    print(space.get("space_id") or space.get("id") or space)


if __name__ == "__main__":
    main()
