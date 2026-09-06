"""C5 handoff selection — offline, no target needed."""

from staticpulse.bridge import build_handoff, selectable, write_handoff
from staticpulse.schemas.finding import Finding


def _f(**kw):
    base = dict(id="1", source="semgrep", title="t", severity="high", confidence=0.7)
    base.update(kw)
    return Finding(**base)


def test_sqli_is_selectable():
    assert selectable(_f(rule_id="python.sqli.x", title="SQL injection")) is True


def test_hardcoded_secret_not_selectable():
    # Can't confirm a secret-at-rest by calling the app.
    assert selectable(_f(source="gitleaks", title="AWS key", severity="critical")) is False


def test_false_positive_excluded():
    assert selectable(_f(title="SQL injection", false_positive=True)) is False


def test_handoff_payload():
    findings = [_f(rule_id="sqli", title="SQL injection"), _f(id="2", title="weak MD5", severity="medium")]
    payload = build_handoff(findings, target="http://127.0.0.1:5000")
    assert payload["count"] == 1
    assert payload["candidates"][0]["suggested_probe"]


def test_write_handoff(tmp_path):
    out = tmp_path / "handoff.json"
    n = write_handoff([_f(rule_id="sqli", title="SQLi")], target="http://127.0.0.1:5000", out_path=out)
    assert n == 1 and out.exists()
