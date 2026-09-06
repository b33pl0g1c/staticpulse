"""The Finding schema — the one object every scanner produces and every
later stage consumes.

Keeping a single normalized shape (instead of each scanner's raw output)
is what lets the normalizer, policy engine, and report all stay simple.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Ordered weakest -> strongest so the policy engine can compare with an index.
Severity = Literal["info", "low", "medium", "high", "critical"]
SEVERITY_ORDER: dict[str, int] = {
    "info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4,
}


class Finding(BaseModel):
    """One security finding, normalized across all sources."""

    # `extra="ignore"`: scanners hand us dicts with keys we don't model, and
    # we don't want a stray key to crash validation.
    model_config = {"extra": "ignore"}

    id: str                       # stable content hash — see schemas/ids.py
    source: str                   # "semgrep" | "gitleaks" | "ai_discovery" ...
    severity: Severity = "medium"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    title: str
    description: str = ""

    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None

    rule_id: str | None = None
    cwe: list[str] = Field(default_factory=list)

    evidence: str = ""            # the offending source lines, for the report

    # Set by the exploitability agent (Phase 2). Deterministic stages never
    # trust the LLM to be present, so these all have safe defaults.
    false_positive: bool = False
    false_positive_reason: str | None = None

    # Set by the patch agent (Phase 3). A patch is only "verified" if the
    # scanner stops reporting the finding after the fix is applied to a
    # throwaway copy of the tree. Nothing is ever auto-applied.
    patch_status: str = "none"          # none|suggested|verified|unverified|not_applicable
    patch_replacement: str | None = None
    patch_explanation: str | None = None
    patch_note: str | None = None
