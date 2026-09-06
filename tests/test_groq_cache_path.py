"""Verify GroqClient's cache + budget wiring WITHOUT network: stub the one
HTTP method and prove the second identical call is served from cache (0 new
tokens, 0 new HTTP calls, budget unchanged)."""

import json

from staticpulse.llm.budget import BudgetTracker
from staticpulse.llm.cache import ResponseCache
from staticpulse.llm.groq_client import GroqClient
from staticpulse.schemas.llm_outputs import ExploitabilityResult


class CountingGroq(GroqClient):
    http_calls = 0
    def _call(self, system, user, temperature, max_tokens):
        type(self).http_calls += 1
        payload = json.dumps({
            "exploitability": "high", "adjusted_severity": "high",
            "adjusted_confidence": 0.9, "false_positive": False,
            "false_positive_reason": None, "reasoning": "ok",
        })
        return payload, 100, 20   # content, tokens_in, tokens_out


def test_second_call_is_cache_hit(tmp_path):
    CountingGroq.http_calls = 0
    cache = ResponseCache(tmp_path, enabled=True)
    budget = BudgetTracker()
    client = CountingGroq(api_key="x", cache=cache, budget=budget)

    kw = dict(system="s", user="u", schema=ExploitabilityResult, prompt_version="exploitability@v1")

    r1 = client.complete(**kw)
    assert r1.cache_hit is False
    assert CountingGroq.http_calls == 1
    assert budget.snapshot() == {"tokens_in": 100, "tokens_out": 20, "llm_calls": 1}

    r2 = client.complete(**kw)
    assert r2.cache_hit is True                 # served from disk
    assert CountingGroq.http_calls == 1         # no new HTTP call
    assert budget.snapshot()["llm_calls"] == 1  # budget untouched
    assert r2.parsed.adjusted_confidence == 0.9
