"""Structured outputs the LLM must return. The model is prompted for JSON and
its reply is validated against these — anything malformed is a validation
error the client retries once, then gives up (the finding keeps its pre-LLM
values). We never `eval` or trust free-form model text.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from staticpulse.schemas.finding import Severity


class ExploitabilityResult(BaseModel):
    """The LLM's second opinion on one scanner finding."""

    model_config = {"extra": "ignore"}

    exploitability: Literal["low", "medium", "high"] = "medium"
    adjusted_severity: Severity = "medium"
    adjusted_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    false_positive: bool = False
    false_positive_reason: str | None = None
    reasoning: str = ""


class PatchSuggestion(BaseModel):
    """The LLM's proposed fix for one finding: replacement code for the
    offending line range, plus a one-line explanation. We never apply the
    unified-diff-from-the-model directly — we splice `replacement_code` into
    the exact line range ourselves, which small models get right far more
    often than they format diffs."""

    model_config = {"extra": "ignore"}

    replacement_code: str = ""
    explanation: str = ""
    unfixable: bool = False   # model may decline if the fix needs broader change
