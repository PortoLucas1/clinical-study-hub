import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "pipeline"))

import dq_rules  # noqa: E402
from dq_rules import OBSERVE, QUARANTINE, RULES, SUBJECT_DOMAINS, expectations, issues_sql, rules_for  # noqa: E402


def test_rules_are_unique_per_domain():
    keys = [(r.domain, r.rule_id) for r in RULES]
    assert len(keys) == len(set(keys))


def test_every_rule_has_a_known_action_and_severity():
    for r in RULES:
        assert r.action in (QUARANTINE, OBSERVE), r
        assert r.severity in ("High", "Medium", "Low"), r


def test_every_subject_domain_checks_subject_id_and_demographics_link():
    for d in SUBJECT_DOMAINS:
        ids = {r.rule_id for r in rules_for(d, QUARANTINE)}
        assert "KEY01" in ids, d
        if d != "dm":
            assert "REF01" in ids, d


def test_observe_rules_are_limited_to_protocol_deviations():
    assert {(r.domain, r.rule_id) for r in RULES if r.action == OBSERVE} == {("sv", "SV01"), ("ae", "AE02")}


def test_expectations_cover_every_rule_and_treat_null_as_failure():
    for d in ["study", *SUBJECT_DOMAINS]:
        exp = expectations(d)
        assert len(exp) == len(rules_for(d))
        assert all(v.startswith("coalesce((") and v.endswith("), false)") for v in exp.values())


def test_issues_sql_is_typed_even_without_rules():
    assert issues_sql("ex", OBSERVE).startswith("CAST(array() AS ARRAY<STRUCT<")
    assert "'DT01'" in issues_sql("ex", QUARANTINE)


def test_rules_rows_match_registry():
    assert len(dq_rules.rules_rows()) == len(RULES) == 40
