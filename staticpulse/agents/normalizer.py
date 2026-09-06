"""Normalize + scope findings.

Two jobs:
  1. De-duplicate by stable ID (two scanners, or two rules, on the same issue).
  2. Diff-scope: drop findings on files/lines the PR didn't touch. On a real
     PR this is the single biggest noise reduction.

Kept intentionally small for v1 (no co-location collapse or taint-floor yet) —
those are later refinements. Start correct, add later.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from staticpulse.schemas.finding import Finding
from staticpulse.tools.git_diff import DiffResult

# Sources whose findings we line-filter. A leaked secret on an untouched line
# is still leaked, so credential/dep findings stay file-scoped, not line-scoped.
_LINE_FILTER_SOURCES = frozenset({"semgrep", "bandit", "sast"})


def _norm(path: str | None) -> str:
    if not path:
        return ""
    return str(PurePosixPath(path.replace("\\", "/").lstrip("./"))).lower()


def normalize(findings: list[Finding], diff: DiffResult) -> list[Finding]:
    # 1. Dedup by ID.
    by_id: dict[str, Finding] = {}
    for f in findings:
        by_id.setdefault(f.id, f)
    deduped = list(by_id.values())

    # 2. Scope to changed files (skip when we have no diff — fallback mode).
    if diff.changed_files:
        changed = {_norm(p) for p in diff.changed_files}
        deduped = [f for f in deduped if not f.file_path or _norm(f.file_path) in changed]

    # 3. Scope SAST findings to changed lines within those files.
    if diff.changed_line_ranges:
        ranges = {_norm(f): rs for f, rs in diff.changed_line_ranges.items()}
        deduped = [f for f in deduped if _line_in_scope(f, ranges)]

    # Deterministic order so reports diff cleanly run-to-run.
    return sorted(deduped, key=lambda f: (f.file_path or "", f.start_line or 0, f.source))


def _line_in_scope(
    f: Finding,
    ranges: dict[str, list[tuple[int, int]]],
    tolerance: int = 2,
) -> bool:
    if f.source not in _LINE_FILTER_SOURCES:
        return True
    if not f.file_path or not f.start_line:
        return True
    file_ranges = ranges.get(_norm(f.file_path))
    if not file_ranges:
        # File changed but no line info captured — keep, don't silently drop.
        return True
    start = f.start_line
    end = f.end_line or start
    for lo, hi in file_ranges:
        if not (end < lo - tolerance or start > hi + tolerance):
            return True
    return False
