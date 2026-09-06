"""Stable finding IDs.

The same vulnerability must get the same ID every run, so that:
  - re-pushing a PR doesn't create "new" findings for the same issue, and
  - a reviewer's "this is a false positive" verdict (Phase 3, C4) can be
    remembered by ID across pushes.

We hash the *identity* of a finding (what it is + where it is), NOT volatile
fields like confidence or the surrounding code text, which can shift by a
line between runs.
"""

from __future__ import annotations

import hashlib


def compute_finding_id(
    *,
    source: str,
    rule_id: str | None,
    file_path: str | None,
    start_line: int | None,
    title: str,
) -> str:
    """Return a short, deterministic hex ID for a finding."""
    parts = [
        source or "",
        rule_id or "",
        (file_path or "").replace("\\", "/"),
        str(start_line or 0),
        # title anchors AI findings, which have no rule_id; for scanner
        # findings rule_id already dominates so title adds little noise.
        title.strip().lower(),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]
