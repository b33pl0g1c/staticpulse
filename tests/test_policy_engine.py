"""The deterministic decision must be right with NO LLM in the loop."""

from staticpulse.policy.engine import decide
from staticpulse.schemas.finding import Finding


def _f(**kw):
    base = dict(id="x", source="semgrep", title="t")
    base.update(kw)
    return Finding(**base)


def test_clean_passes():
    assert decide([]).status == "PASS"


def test_high_impact_sqli_fails():
    f = _f(rule_id="python.lang.security.sqli.tainted-sql-string",
           title="SQL injection", severity="high", confidence=0.6)
    assert decide([f]).status == "FAIL"


def test_critical_secret_fails():
    f = _f(source="gitleaks", title="AWS key", severity="critical", confidence=0.9)
    assert decide([f]).status == "FAIL"


def test_medium_non_impact_warns():
    f = _f(rule_id="weak-hash", title="MD5 used", severity="medium", confidence=0.6)
    assert decide([f]).status == "WARN"


def test_false_positive_is_ignored():
    f = _f(rule_id="sqli", title="SQLi", severity="high", confidence=0.9, false_positive=True)
    assert decide([f]).status == "PASS"
