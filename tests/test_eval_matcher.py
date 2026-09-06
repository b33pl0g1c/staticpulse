"""Matcher: labels <-> findings, TP/FP/FN."""

from staticpulse.eval.matcher import match
from staticpulse.eval.schema import ExpectedLabel
from staticpulse.schemas.finding import Finding


def _f(**kw):
    base = dict(id="1", source="semgrep", title="SQL injection",
                rule_id="python.sqli.x", file_path="db.py", start_line=4)
    base.update(kw)
    return Finding(**base)


def _lbl(**kw):
    base = dict(file="db.py", type="sqli", line_range=[4, 5])
    base.update(kw)
    return ExpectedLabel(**base)


def test_true_positive():
    r = match([_f()], [_lbl()])
    assert (r.tp, r.fp, r.fn) == (1, 0, 0)


def test_false_negative_when_no_finding():
    r = match([], [_lbl()])
    assert (r.tp, r.fp, r.fn) == (0, 0, 1)


def test_false_positive_extra_finding():
    extra = _f(id="2", title="MD5", rule_id="weak-hash", start_line=99)
    r = match([_f(), extra], [_lbl()])
    assert r.tp == 1 and r.fp == 1


def test_wrong_line_is_not_matched():
    r = match([_f(start_line=100, end_line=100)], [_lbl()])
    assert r.fn == 1 and r.tp == 0


def test_false_positive_finding_excluded():
    r = match([_f(false_positive=True)], [_lbl()])
    assert r.fn == 1 and r.fp == 0
