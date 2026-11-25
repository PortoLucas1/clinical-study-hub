"""Generate synthetic clinical study packages (zip) that mimic what a CRO receives
from sponsors: EDC exports as CSV, central-lab vendor data as Excel, and a
protocol metadata JSON (ClinicalTrials.gov style).

Usage:
    uv run --with openpyxl python src/data_gen/generate_studies.py --out data/samples
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook


@dataclass
class StudySpec:
    study_id: str
    title: str
    phase: str
    indication: str
    therapeutic_area: str
    sponsor: str
    nct_id: str
    arms: list[str]
    n_subjects: int
    planned_enrollment: int
    n_sites: int
    countries: list[str]
    start: date
    treatment: dict[str, tuple[str, float, str]]
    ae_profile: dict[str, list[str]]
    drug_arm: str
    lab_signal: tuple[str, float]
    extra_columns: bool = False
    seed: int = 7
    sites: list[str] = field(default_factory=list)


AE_BASE = {
    "Gastrointestinal disorders": ["Nausea", "Diarrhoea", "Vomiting", "Constipation"],
    "General disorders": ["Fatigue", "Pyrexia", "Oedema peripheral", "Asthenia"],
    "Nervous system disorders": ["Headache", "Dizziness", "Neuropathy peripheral"],
    "Skin and subcutaneous tissue disorders": ["Rash", "Pruritus", "Alopecia"],
    "Infections and infestations": ["Upper respiratory tract infection", "Pneumonia", "Urinary tract infection"],
    "Blood and lymphatic system disorders": ["Anaemia", "Neutropenia", "Thrombocytopenia"],
}

LABS = {
    "ALT": ("U/L", 7.0, 56.0, 28.0, 10.0),
    "AST": ("U/L", 10.0, 40.0, 24.0, 8.0),
    "CREATININE": ("mg/dL", 0.6, 1.3, 0.95, 0.18),
    "HEMOGLOBIN": ("g/dL", 12.0, 17.5, 14.0, 1.4),
    "WBC": ("10^9/L", 4.0, 11.0, 7.0, 1.8),
    "PLATELETS": ("10^9/L", 150.0, 400.0, 260.0, 55.0),
    "POTASSIUM": ("mmol/L", 3.5, 5.1, 4.3, 0.35),
    "GLUCOSE": ("mg/dL", 70.0, 99.0, 90.0, 12.0),
}

VITALS = {
    "SYSBP": ("mmHg", 124.0, 14.0),
    "DIABP": ("mmHg", 79.0, 9.0),
    "HR": ("beats/min", 74.0, 10.0),
    "TEMP": ("C", 36.7, 0.3),
    "WEIGHT": ("kg", 78.0, 14.0),
}

VISITS = [("SCREENING", -14), ("BASELINE", 0), ("WEEK 4", 28), ("WEEK 8", 56), ("WEEK 12", 84), ("WEEK 24", 168)]


STUDIES = [
    StudySpec(
        study_id="ONC-101",
        title="A Phase II, Randomized, Open-Label Study of SMX-401 Versus Docetaxel in Previously Treated Advanced Non-Small Cell Lung Cancer",
        phase="Phase 2",
        indication="Non-Small Cell Lung Cancer",
        therapeutic_area="Oncology",
        sponsor="Synthetic Biopharma Inc.",
        nct_id="NCT0SYN0101",
        arms=["SMX-401 200 mg", "Docetaxel 75 mg/m2"],
        n_subjects=124,
        planned_enrollment=150,
        n_sites=8,
        countries=["USA", "Canada", "Spain", "Germany"],
        start=date(2025, 3, 3),
        treatment={"SMX-401 200 mg": ("SMX-401", 200, "mg"), "Docetaxel 75 mg/m2": ("DOCETAXEL", 75, "mg/m2")},
        ae_profile={
            "Hepatobiliary disorders": ["Hepatotoxicity", "Transaminases increased"],
            "Respiratory, thoracic and mediastinal disorders": ["Dyspnoea", "Cough", "Pneumonitis"],
        },
        drug_arm="SMX-401 200 mg",
        lab_signal=("ALT", 2.2),
        seed=101,
    ),
    StudySpec(
        study_id="CARD-202",
        title="A Phase III, Double-Blind, Placebo-Controlled Study of CRD-7 in Patients with Heart Failure with Reduced Ejection Fraction",
        phase="Phase 3",
        indication="Heart Failure with Reduced Ejection Fraction",
        therapeutic_area="Cardiovascular",
        sponsor="Synthetic Cardio Therapeutics",
        nct_id="NCT0SYN0202",
        arms=["CRD-7 10 mg", "Placebo"],
        n_subjects=236,
        planned_enrollment=300,
        n_sites=12,
        countries=["USA", "Brazil", "India", "United Kingdom", "Japan"],
        start=date(2024, 11, 4),
        treatment={"CRD-7 10 mg": ("CRD-7", 10, "mg"), "Placebo": ("PLACEBO", 0, "mg")},
        ae_profile={
            "Cardiac disorders": ["Atrial fibrillation", "Palpitations", "Cardiac failure"],
            "Metabolism and nutrition disorders": ["Hyperkalaemia", "Dehydration"],
            "Vascular disorders": ["Hypotension", "Orthostatic hypotension"],
        },
        drug_arm="CRD-7 10 mg",
        lab_signal=("POTASSIUM", 1.18),
        extra_columns=True,
        seed=202,
    ),
    StudySpec(
        study_id="RESP-303",
        title="A Phase II Study of Inhaled RSP-12 in Adults with Moderate-to-Severe Asthma",
        phase="Phase 2",
        indication="Moderate-to-Severe Asthma",
        therapeutic_area="Respiratory",
        sponsor="Synthetic Airway Sciences",
        nct_id="NCT0SYN0303",
        arms=["RSP-12 100 mcg", "Placebo"],
        n_subjects=88,
        planned_enrollment=120,
        n_sites=6,
        countries=["USA", "France", "Australia"],
        start=date(2025, 6, 2),
        treatment={"RSP-12 100 mcg": ("RSP-12", 100, "mcg"), "Placebo": ("PLACEBO", 0, "mcg")},
        ae_profile={
            "Respiratory, thoracic and mediastinal disorders": ["Asthma exacerbation", "Dysphonia", "Oropharyngeal pain"],
            "Infections and infestations": ["Oral candidiasis", "Nasopharyngitis"],
        },
        drug_arm="RSP-12 100 mcg",
        lab_signal=("WBC", 1.05),
        seed=303,
    ),
]


def fmt(d: date | None) -> str:
    return d.isoformat() if d else ""


def to_csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def build_study(spec: StudySpec) -> dict[str, bytes]:
    rnd = random.Random(spec.seed)
    spec.sites = [f"{100 + i:03d}" for i in range(1, spec.n_sites + 1)]
    site_country = {s: spec.countries[i % len(spec.countries)] for i, s in enumerate(spec.sites)}
    today = date(2026, 11, 2)
    enrollment_days = (today - spec.start).days - 45

    dm_rows, ae_rows, vs_rows, ex_rows, ds_rows, sv_rows, lb_rows = [], [], [], [], [], [], []
    ae_catalog = {**AE_BASE, **spec.ae_profile}

    for n in range(1, spec.n_subjects + 1):
        site = rnd.choice(spec.sites)
        subj = f"{spec.study_id}-{site}-{n:04d}"
        arm = spec.arms[n % len(spec.arms)]
        is_drug = arm == spec.drug_arm
        consent = spec.start + timedelta(days=int(rnd.betavariate(1.4, 1.6) * enrollment_days))
        rand_date = consent + timedelta(days=rnd.randint(7, 21))
        age = max(18, min(88, int(rnd.gauss(62 if spec.therapeutic_area != "Respiratory" else 45, 11))))
        sex = rnd.choice(["M", "F"])
        race = rnd.choices(
            ["WHITE", "BLACK OR AFRICAN AMERICAN", "ASIAN", "AMERICAN INDIAN OR ALASKA NATIVE", "OTHER"],
            weights=[55, 15, 20, 3, 7],
        )[0]
        ethnicity = rnd.choices(["NOT HISPANIC OR LATINO", "HISPANIC OR LATINO"], weights=[80, 20])[0]

        # Deliberate data quality issues for the automated data quality checks.
        dq_age = age
        if rnd.random() < 0.015:
            dq_age = rnd.choice([7, 142])
        dq_consent = consent if rnd.random() > 0.02 else None

        row = [subj, site, arm, sex, dq_age, race, ethnicity, site_country[site], fmt(dq_consent), fmt(rand_date)]
        if spec.extra_columns:
            row.append(round(rnd.gauss(29.5, 5.0), 1))
        dm_rows.append(row)

        # Disposition
        days_on_study = (today - rand_date).days
        r = rnd.random()
        if days_on_study < 168:
            status, reason, ds_date = "ONGOING", "", None
        elif r < (0.22 if is_drug else 0.16):
            status = "DISCONTINUED"
            reason = rnd.choice(["ADVERSE EVENT", "WITHDRAWAL BY SUBJECT", "PROGRESSIVE DISEASE", "LOST TO FOLLOW-UP", "PHYSICIAN DECISION"])
            ds_date = rand_date + timedelta(days=rnd.randint(30, 160))
        else:
            status, reason, ds_date = "COMPLETED", "", rand_date + timedelta(days=168 + rnd.randint(0, 10))
        ds_rows.append([subj, status, reason, fmt(ds_date)])
        last_day = (ds_date or today) - rand_date

        # Exposure
        drug, dose, unit = spec.treatment[arm]
        ex_rows.append([subj, drug, dose, unit, fmt(rand_date), fmt(ds_date)])

        # Visits, vitals and labs
        for visit, offset in VISITS:
            planned = rand_date + timedelta(days=offset)
            if offset > last_day.days or planned > today:
                continue
            actual = planned + timedelta(days=rnd.randint(-3, 6))
            if rnd.random() < 0.04:
                actual = planned + timedelta(days=rnd.randint(10, 25))
            sv_rows.append([subj, visit, fmt(planned), fmt(actual)])

            for test, (unit_v, mean, sd) in VITALS.items():
                val = rnd.gauss(mean, sd)
                if test == "SYSBP" and is_drug and spec.therapeutic_area == "Cardiovascular" and offset > 0:
                    val -= 6
                if rnd.random() < 0.004:
                    val = val * 10
                vs_rows.append([subj, visit, fmt(actual), test, round(val, 1), unit_v])

            if visit == "SCREENING" or offset >= 28 or visit == "BASELINE":
                for test, (unit_l, low, high, mean, sd) in LABS.items():
                    val = rnd.gauss(mean, sd)
                    sig_test, factor = spec.lab_signal
                    if test == sig_test and is_drug and offset > 0:
                        val *= factor if rnd.random() < 0.35 else 1.05
                    result: object = round(max(val, 0.1), 2)
                    if rnd.random() < 0.003:
                        result = rnd.choice(["<LLOQ", "HEMOLYZED", ""])
                    lb_rows.append([subj, test, result, unit_l, low, high, actual, visit])

        # Adverse events
        n_ae = rnd.choices([0, 1, 2, 3, 4, 5], weights=[18, 25, 22, 15, 12, 8])[0] + (1 if is_drug else 0)
        for _ in range(n_ae):
            if last_day.days <= 1:
                break
            soc = rnd.choice(list(ae_catalog.keys()))
            if soc in spec.ae_profile and not is_drug and rnd.random() < 0.5:
                soc = rnd.choice(list(AE_BASE.keys()))
            term = rnd.choice(ae_catalog[soc])
            grade = rnd.choices([1, 2, 3, 4, 5], weights=[45, 32, 16, 5, 0.6 if is_drug else 0.3])[0]
            serious = "Y" if grade >= 3 and rnd.random() < 0.55 else "N"
            related = rnd.choices(["Y", "N"], weights=[55 if is_drug else 25, 45 if is_drug else 75])[0]
            onset = rand_date + timedelta(days=rnd.randint(1, max(2, last_day.days)))
            end = onset + timedelta(days=rnd.randint(2, 40))
            outcome = "FATAL" if grade == 5 else rnd.choice(["RECOVERED/RESOLVED", "RECOVERING/RESOLVING", "NOT RECOVERED/NOT RESOLVED"])
            if outcome == "NOT RECOVERED/NOT RESOLVED":
                end = None
            if rnd.random() < 0.01 and end:
                end = onset - timedelta(days=5)
            ae = [subj, term, soc, grade, serious, related, fmt(onset), fmt(end), outcome]
            if spec.extra_columns:
                ae.append(rnd.choice(["DOSE NOT CHANGED", "DOSE REDUCED", "DRUG INTERRUPTED", "DRUG WITHDRAWN"]))
            ae_rows.append(ae)

    dm_header = ["SUBJECT_ID", "SITE_ID", "ARM", "SEX", "AGE", "RACE", "ETHNICITY", "COUNTRY", "CONSENT_DATE", "RANDOMIZATION_DATE"]
    ae_header = ["SUBJECT_ID", "AE_TERM", "BODY_SYSTEM", "SEVERITY_GRADE", "SERIOUS", "RELATED", "ONSET_DATE", "END_DATE", "OUTCOME"]
    if spec.extra_columns:
        dm_header.append("BMI")
        ae_header.append("ACTION_TAKEN")

    files = {
        "edc/demographics.csv": to_csv(dm_header, dm_rows),
        "edc/adverse_events.csv": to_csv(ae_header, ae_rows),
        "edc/vital_signs.csv": to_csv(["SUBJECT_ID", "VISIT", "VISIT_DATE", "TEST", "RESULT", "UNIT"], vs_rows),
        "edc/exposure.csv": to_csv(["SUBJECT_ID", "TREATMENT", "DOSE", "DOSE_UNIT", "START_DATE", "END_DATE"], ex_rows),
        "edc/disposition.csv": to_csv(["SUBJECT_ID", "STATUS", "REASON", "DISPOSITION_DATE"], ds_rows),
        "edc/site_visits.csv": to_csv(["SUBJECT_ID", "VISIT", "PLANNED_DATE", "ACTUAL_DATE"], sv_rows),
        "vendor/central_lab_results.xlsx": lab_workbook(lb_rows),
    }

    metadata = {
        "study_id": spec.study_id,
        "nct_id": spec.nct_id,
        "title": spec.title,
        "phase": spec.phase,
        "indication": spec.indication,
        "therapeutic_area": spec.therapeutic_area,
        "sponsor": spec.sponsor,
        "arms": spec.arms,
        "planned_enrollment": spec.planned_enrollment,
        "sites": [{"site_id": s, "country": site_country[s]} for s in spec.sites],
        "study_start_date": fmt(spec.start),
        "data_cutoff_date": fmt(today),
        "package_version": "1.0",
        "files": {k: {"domain": domain_for(k)} for k in files},
    }
    files["study_metadata.json"] = json.dumps(metadata, indent=2).encode("utf-8")
    return files


def domain_for(path: str) -> str:
    return {
        "demographics": "dm",
        "adverse_events": "ae",
        "vital_signs": "vs",
        "exposure": "ex",
        "disposition": "ds",
        "site_visits": "sv",
        "central_lab_results": "lb",
    }[Path(path).stem]


def lab_workbook(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    ws.append(["Patient", "Lab Test", "Result Value", "Units", "Ref Low", "Ref High", "Collection Date", "Visit"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/samples")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for spec in STUDIES:
        files = build_study(spec)
        zpath = out / f"{spec.study_id}_study_package.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for name, content in files.items():
                z.writestr(f"{spec.study_id}/{name}", content)
        print(f"wrote {zpath} ({zpath.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
