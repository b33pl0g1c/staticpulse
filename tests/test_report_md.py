"""PR summary + inline comment rendering — pure, offline."""

from staticpulse.orchestrator import RunResult
from staticpulse.policy.engine import Decision
from staticpulse.report_md import build_inline_comments, render_summary
from staticpulse.schemas.finding import Finding


def _f(**kw):
    base = dict(id="1", source="semgrep", title="SQL injection",
                rule_id="python.sqli", severity="high", confidence=0.7,
                file_path="db.py", start_line=4)
    base.update(kw)
    return Finding(**base)


def _result(findings, status="FAIL", **kw):
    d = Decision(status=status, risk_score=50, reasons=["x"])
    return RunResult(decision=d, findings=findings, changed_files=["db.py"], **kw)


def test_summary_has_status_and_table():
    md = render_summary(_result([_f()]))
    assert "StaticPulse — FAIL" in md
    assert "db.py:4" in md and "SQL injection" in md


def test_summary_renders_verified_suggestion_block():
    f = _f(patch_status="verified", patch_replacement="cur.execute(q, (uid,))",
           patch_explanation="parameterized")
    md = render_summary(_result([f]))
    assert "verified fix" in md.lower()
    assert "```suggestion" in md and "cur.execute(q, (uid,))" in md


def test_summary_notes_suppressions():
    md = render_summary(_result([_f()], suppressed=2))
    assert "2 finding(s) suppressed" in md


def test_inline_comments_built_for_located_findings():
    comments = build_inline_comments([_f()])
    assert comments == [{"path": "db.py", "line": 4,
                         "body": comments[0]["body"]}]
    assert "HIGH: SQL injection" in comments[0]["body"]


def test_inline_skips_fp_and_unlocated():
    fp = _f(id="2", false_positive=True)
    noloc = _f(id="3", file_path=None, start_line=None)
    assert build_inline_comments([fp, noloc]) == []
