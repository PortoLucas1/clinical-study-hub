"""Mock AI-assisted data modelling: propose source-to-SDTM column mappings, validate them, retry with feedback.

This stands in for an AI step (for example an agent that proposes how vendor columns map to SDTM variables)
that runs before the Lakeflow Declarative Pipelines. The proposal is SIMULATED so the demo is deterministic;
the validation against the golden mapping spec, the accuracy calculation and the retry loop are real.

Accuracy is value-weighted: every mapped column counts once per row of its file, so one wrong column in a
file with 100 rows is 100 wrong values. With about 40 columns per study, a column-count accuracy would make a
99.9% threshold mean "100%"; weighting by values keeps the threshold meaningful.

Scenarios (the `ai_demo_scenario` job parameter):
- `pass`: the first proposal is correct.
- `recover`: attempts 1 and 2 contain wrong mappings, attempt 3 (the second retry) is correct.
- `fail`: one stubborn wrong mapping never gets fixed, so the human fallback takes over.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

SCENARIOS = ("pass", "recover", "fail")

# Golden mapping: source column (normalized header) -> SDTM-style variable, per domain.
SPEC: dict[str, dict[str, str]] = {
    "dm": {
        "SUBJECT_ID": "USUBJID", "SITE_ID": "SITEID", "ARM": "ARM", "SEX": "SEX", "AGE": "AGE", "RACE": "RACE",
        "ETHNICITY": "ETHNIC", "COUNTRY": "COUNTRY", "CONSENT_DATE": "RFICDTC", "RANDOMIZATION_DATE": "RANDDT",
        "BMI": "BMI",
    },
    "ae": {
        "SUBJECT_ID": "USUBJID", "AE_TERM": "AETERM", "BODY_SYSTEM": "AESOC", "SEVERITY_GRADE": "AETOXGR",
        "SERIOUS": "AESER", "RELATED": "AEREL", "ONSET_DATE": "AESTDTC", "END_DATE": "AEENDTC",
        "OUTCOME": "AEOUT", "ACTION_TAKEN": "AEACN",
    },
    "vs": {
        "SUBJECT_ID": "USUBJID", "VISIT": "VISIT", "VISIT_DATE": "VSDTC", "TEST": "VSTESTCD",
        "RESULT": "VSORRES", "UNIT": "VSSTRESU",
    },
    "lb": {
        "PATIENT": "USUBJID", "LAB_TEST": "LBTESTCD", "RESULT_VALUE": "LBORRES", "UNITS": "LBSTRESU",
        "REF_LOW": "LBORNRLO", "REF_HIGH": "LBORNRHI", "COLLECTION_DATE": "LBDTC", "VISIT": "VISIT",
    },
    "ex": {
        "SUBJECT_ID": "USUBJID", "TREATMENT": "EXTRT", "DOSE": "EXDOSE", "DOSE_UNIT": "EXDOSU",
        "START_DATE": "EXSTDTC", "END_DATE": "EXENDTC",
    },
    "ds": {"SUBJECT_ID": "USUBJID", "STATUS": "DSDECOD", "REASON": "DSTERM", "DISPOSITION_DATE": "DSSTDTC"},
    "sv": {
        "SUBJECT_ID": "USUBJID", "VISIT": "VISIT", "PLANNED_DATE": "SVPLDTC", "ACTUAL_DATE": "SVSTDTC",
    },
}

Mapping = dict[tuple[str, str], str]  # (domain, source column) -> SDTM variable


@dataclass
class Validation:
    accuracy_pct: float
    values_checked: int
    values_wrong: int
    wrong_columns: list[str]


@dataclass
class Attempt:
    attempt: int
    scenario: str
    accuracy_pct: float
    values_checked: int
    values_wrong: int
    wrong_columns: list[str]
    outcome: str  # pass | retry | fail
    feedback: str = ""


@dataclass
class ModellingResult:
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def final(self) -> Attempt:
        return self.attempts[-1]

    @property
    def passed(self) -> bool:
        return self.final.outcome == "pass"


def golden_mapping(domain_columns: dict[str, list[str]]) -> Mapping:
    """The correct mapping for the columns that exist in the package (columns outside the spec are not modelled)."""
    return {
        (d, c): SPEC[d][c]
        for d, cols in domain_columns.items()
        if d in SPEC
        for c in cols
        if c in SPEC[d]
    }


def _fault_order(golden: Mapping, seed: str) -> list[tuple[str, str]]:
    """Deterministic order in which the mock model makes mistakes (key columns are never the ones it gets wrong)."""
    candidates = [k for k, v in golden.items() if v != "USUBJID"]
    return sorted(candidates, key=lambda k: hashlib.sha256(f"{seed}:{k[0]}:{k[1]}".encode()).hexdigest())


def faults_for(scenario: str, attempt: int) -> int:
    """How many columns the mock model gets wrong on a given attempt (1-based)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown ai_demo_scenario '{scenario}', expected one of {', '.join(SCENARIOS)}")
    if scenario == "pass":
        return 0
    if scenario == "recover":
        return {1: 2, 2: 1}.get(attempt, 0)
    return 1  # fail: a stubborn mistake that retries cannot fix


def propose(golden: Mapping, scenario: str, attempt: int, seed: str) -> Mapping:
    """Simulated AI proposal: the golden mapping with a scenario-driven number of swapped targets."""
    proposal = dict(golden)
    for domain, col in _fault_order(golden, seed)[: faults_for(scenario, attempt)]:
        siblings = sorted(c for (d, c) in golden if d == domain)
        if len(siblings) < 2:
            continue
        other = siblings[(siblings.index(col) + 1) % len(siblings)]
        proposal[(domain, col)] = golden[(domain, other)]
        if golden[(domain, other)] == golden[(domain, col)]:  # same target, pick the next sibling
            other = siblings[(siblings.index(col) + 2) % len(siblings)]
            proposal[(domain, col)] = golden[(domain, other)]
    return proposal


def validate(proposal: Mapping, golden: Mapping, rows_by_domain: dict[str, int]) -> Validation:
    """Compares a proposal with the golden mapping, weighting each column by the rows of its file."""
    checked = wrong = 0
    wrong_cols: list[str] = []
    for key, target in golden.items():
        weight = max(int(rows_by_domain.get(key[0], 0)), 1)
        checked += weight
        if proposal.get(key) != target:
            wrong += weight
            wrong_cols.append(f"{key[0]}.{key[1]}")
    accuracy = 100.0 if checked == 0 else 100.0 * (checked - wrong) / checked
    # Truncate, never round up: 99.9996 must not become 100.0 and slip past the gate.
    return Validation(math.floor(accuracy * 1000) / 1000, checked, wrong, sorted(wrong_cols))


def run_modelling(
    domain_columns: dict[str, list[str]],
    rows_by_domain: dict[str, int],
    scenario: str = "pass",
    threshold_pct: float = 99.9,
    max_retries: int = 3,
    seed: str = "",
) -> ModellingResult:
    """One attempt plus up to `max_retries` retries; each retry is told which columns were wrong."""
    scenario = (scenario or "pass").strip().lower()
    faults_for(scenario, 1)  # validates the scenario name
    golden = golden_mapping(domain_columns)
    result = ModellingResult()
    feedback = ""
    for attempt in range(1, max_retries + 2):
        proposal = propose(golden, scenario, attempt, seed)
        v = validate(proposal, golden, rows_by_domain)
        if v.accuracy_pct >= threshold_pct:
            outcome = "pass"
        elif attempt <= max_retries:
            outcome = "retry"
        else:
            outcome = "fail"
        result.attempts.append(
            Attempt(attempt, scenario, v.accuracy_pct, v.values_checked, v.values_wrong, v.wrong_columns, outcome, feedback)
        )
        if outcome != "retry":
            break
        feedback = "Wrong mappings in the previous attempt: " + ", ".join(v.wrong_columns)
    return result
