"""One per-PR cost guardrail, shared across every LLM stage.

The tracker is created once in the orchestrator and threaded into every LLM
stage. The tempting shortcut — letting each agent construct its own tracker —
silently multiplies the real ceiling by the number of agents, so the cap is
enforced in exactly one place and `max_llm_calls` / `max_tokens` mean what
they say.
"""

from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    """A planned call would breach the per-PR cap."""


@dataclass
class BudgetTracker:
    max_llm_calls: int = 50
    max_tokens: int = 200_000
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0
    skipped_reason: str | None = None

    def can_proceed(self) -> bool:
        if self.llm_calls >= self.max_llm_calls:
            self.skipped_reason = f"max_llm_calls={self.max_llm_calls} reached"
            return False
        if self.tokens_in + self.tokens_out >= self.max_tokens:
            self.skipped_reason = f"max_tokens={self.max_tokens} reached"
            return False
        return True

    def record(self, *, tokens_in: int, tokens_out: int) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.llm_calls += 1

    def snapshot(self) -> dict[str, int]:
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "llm_calls": self.llm_calls,
        }
