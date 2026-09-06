"""Report renderer + README injection."""

from staticpulse.eval.matcher import MatchResult
from staticpulse.eval.report import aggregate_table, inject_readme, to_json
from staticpulse.eval.runner import ModeRun, ScenarioResult


def _result():
    r = ScenarioResult(id="sqli", expected_decision="FAIL")
    r.runs["scanners_only"] = ModeRun(
        mode="scanners_only", decision="FAIL", decision_correct=True,
        match=MatchResult(tp=1, fp=0, fn=0), latency_ms=5000)
    return [r]


def test_json_has_aggregate_and_scenarios():
    j = to_json(_result(), ("scanners_only",))
    assert j["aggregate"]["scanners_only"]["decisions_correct"] == 1
    assert j["scenarios"][0]["id"] == "sqli"


def test_table_renders():
    t = aggregate_table(_result(), ("scanners_only",))
    assert "decisions correct" in t and "1/1" in t


def test_readme_injection(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("intro\n<!-- EVAL:START -->\nold\n<!-- EVAL:END -->\nrest\n", encoding="utf-8")
    assert inject_readme(_result(), ("scanners_only",), readme=readme) is True
    text = readme.read_text(encoding="utf-8")
    assert "decisions correct" in text and "old" not in text and "rest" in text
