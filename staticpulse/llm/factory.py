"""Build an LLMClient from the environment, or return None if unavailable.

Returning None (rather than raising) is deliberate: a missing key must degrade
the pipeline to scanners-only, never crash it. The caller reports the gap.

Env:
  STATICPULSE_LLM_PROVIDER   default "groq"
  STATICPULSE_LLM_MODEL      default per provider
  GROQ_API_KEY              required for the groq provider
"""

from __future__ import annotations

import os

from staticpulse.llm.base import LLMClient
from staticpulse.llm.budget import BudgetTracker
from staticpulse.llm.cache import ResponseCache


def build_llm_client(
    *,
    cache: ResponseCache | None = None,
    budget: BudgetTracker | None = None,
) -> tuple[LLMClient | None, str | None]:
    """Return (client, reason_unavailable). Exactly one is non-None."""
    provider = os.environ.get("STATICPULSE_LLM_PROVIDER", "groq").lower()

    if provider == "groq":
        key = os.environ.get("GROQ_API_KEY", "")
        if not key:
            return None, "GROQ_API_KEY not set"
        from staticpulse.llm.groq_client import GroqClient
        model = os.environ.get("STATICPULSE_LLM_MODEL", "openai/gpt-oss-20b")
        return GroqClient(api_key=key, model=model, cache=cache, budget=budget), None

    return None, f"unknown provider {provider!r}"
