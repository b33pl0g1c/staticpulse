"""Match reported findings against a fixture's expected labels.

A label and a finding match when the file matches, the line ranges overlap
(with tolerance), and the label's type aliases to the finding's rule/title.
Greedy 1:1: each finding satisfies at most one label, each label at most one
finding. Leftovers are false positives (findings) or false negatives (labels).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from staticpulse.eval.schema import ExpectedLabel
from staticpulse.schemas.finding import Finding

LINE_TOLERANCE = 5

# label type -> substrings that identify it in a finding's rule_id or title.
_ALIASES: dict[str, tuple[str, ...]] = {
    "sqli": ("sql", "sqli", "injection"),
    "command_injection": ("command", "os-system", "os_system", "subprocess", "shell"),
    "weak_crypto": ("md5", "sha1", "weak", "insecure-hash", "hashlib"),
    "yaml_unsafe": ("yaml", "unsafe"),
    "insecure_deser": ("pickle", "deserial", "loads", "avoid-pickle"),
    "code_injection": ("eval", "code-injection", "exec", "eval-detected"),
    "missing_authz": ("authz", "authorization", "access", "idor", "permission", "auth"),
    "ssrf": ("ssrf", "request-forgery"),
    "path_traversal": ("path-traversal", "traversal"),
    "xss": ("xss", "cross-site"),
    "hardcoded_secret": ("secret", "hardcoded", "api-key", "password"),
}


@dataclass
class MatchResult:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    matched_labels: list[str] = field(default_factory=list)
    unmatched_labels: list[str] = field(default_factory=list)


def _norm(p: str | None) -> str:
    return str(PurePosixPath((p or "").replace("\\", "/").lstrip("./"))).lower()


def _lines_overlap(label: ExpectedLabel, f: Finding) -> bool:
    if not label.line_range:
        return True
    lo, hi = label.line_range[0], label.line_range[-1]
    fs = f.start_line or 0
    fe = f.end_line or fs
    return not (fe < lo - LINE_TOLERANCE or fs > hi + LINE_TOLERANCE)


def _type_matches(label_type: str, f: Finding) -> bool:
    text = f"{f.rule_id or ''} {f.title}".lower()
    return any(a in text for a in _ALIASES.get(label_type, (label_type,)))


def match(findings: list[Finding], labels: list[ExpectedLabel]) -> MatchResult:
    active = [f for f in findings if not f.false_positive]
    used: set[int] = set()
    res = MatchResult()

    for label in labels:
        lpath = _norm(label.file)
        hit: int | None = None
        for i, f in enumerate(active):
            if i in used:
                continue
            if _norm(f.file_path) != lpath:
                continue
            if not _lines_overlap(label, f):
                continue
            if not _type_matches(label.type, f):
                continue
            hit = i
            break
        if hit is not None:
            used.add(hit)
            res.tp += 1
            res.matched_labels.append(f"{label.file}:{label.type}")
        else:
            res.fn += 1
            res.unmatched_labels.append(f"{label.file}:{label.type}")

    res.fp = len(active) - len(used)
    return res
