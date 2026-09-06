"""Labels for an eval fixture. A fixture declares the decision it expects and
the specific weaknesses a good reviewer should surface."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ExpectedLabel(BaseModel):
    file: str
    type: str
    line_range: list[int] | None = None


class Expected(BaseModel):
    expected_decision: Literal["PASS", "WARN", "FAIL"]
    labels: list[ExpectedLabel] = []
