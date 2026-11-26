import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "lib"))

from modelling import SPEC, golden_mapping, propose, run_modelling, validate  # noqa: E402

COLUMNS = {d: list(cols) for d, cols in SPEC.items()}
ROWS = {"dm": 120, "ae": 300, "vs": 900, "lb": 700, "ex": 120, "ds": 120, "sv": 600}


def test_pass_scenario_is_correct_first_time():
    r = run_modelling(COLUMNS, ROWS, "pass", 99.9, 3, seed="NEURO-505")
    assert r.passed and len(r.attempts) == 1
    assert r.final.accuracy_pct == 100.0 and r.final.wrong_columns == []


def test_recover_scenario_needs_three_attempts():
    r = run_modelling(COLUMNS, ROWS, "recover", 99.9, 3, seed="NEURO-505")
    assert [a.outcome for a in r.attempts] == ["retry", "retry", "pass"]
    assert r.attempts[0].accuracy_pct < 99.9 and r.attempts[1].accuracy_pct < 99.9
    assert len(r.attempts[0].wrong_columns) == 2 and len(r.attempts[1].wrong_columns) == 1
    assert r.attempts[1].feedback.startswith("Wrong mappings in the previous attempt")


def test_fail_scenario_exhausts_three_retries():
    r = run_modelling(COLUMNS, ROWS, "fail", 99.9, 3, seed="NEURO-505")
    assert not r.passed
    assert len(r.attempts) == 4  # 1 attempt + 3 retries
    assert [a.outcome for a in r.attempts] == ["retry", "retry", "retry", "fail"]
    assert all(a.accuracy_pct < 99.9 for a in r.attempts)


def test_one_wrong_column_fails_the_gate_but_is_not_zero_accuracy():
    golden = golden_mapping(COLUMNS)
    proposal = propose(golden, "fail", 1, "ONC-101")
    v = validate(proposal, golden, ROWS)
    assert len(v.wrong_columns) == 1
    assert 90 < v.accuracy_pct < 99.9


def test_accuracy_is_truncated_not_rounded_up():
    golden = {("dm", "AGE"): "AGE", ("dm", "ARM"): "ARM"}
    proposal = {("dm", "AGE"): "AGE", ("dm", "ARM"): "WRONG"}
    v = validate(proposal, golden, {"dm": 1})
    assert v.accuracy_pct == 50.0
    big = validate(proposal, golden, {"dm": 1})
    assert big.values_wrong == 1
    many = {("dm", f"C{i}"): f"T{i}" for i in range(1000)}
    bad = dict(many)
    bad[("dm", "C0")] = "X"
    # 1 wrong of 1000 values = 99.9 exactly, which meets a 99.9 threshold
    assert validate(bad, many, {"dm": 1}).accuracy_pct == 99.9
    bad[("dm", "C1")] = "X"
    assert validate(bad, many, {"dm": 1}).accuracy_pct == 99.8


def test_missing_columns_are_not_modelled():
    cols = {"dm": ["SUBJECT_ID", "AGE"], "lb": ["PATIENT"]}
    assert golden_mapping(cols) == {("dm", "SUBJECT_ID"): "USUBJID", ("dm", "AGE"): "AGE", ("lb", "PATIENT"): "USUBJID"}


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError):
        run_modelling(COLUMNS, ROWS, "chaos")


def test_same_seed_is_deterministic():
    a = run_modelling(COLUMNS, ROWS, "recover", seed="CARD-202")
    b = run_modelling(COLUMNS, ROWS, "recover", seed="CARD-202")
    assert [x.wrong_columns for x in a.attempts] == [x.wrong_columns for x in b.attempts]
