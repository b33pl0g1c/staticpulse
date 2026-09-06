"""Regression guards for two live-integration bugs found in this session:
  1. Cloudflare error 1010 — urllib's default User-Agent is blocked, so the
     client MUST send its own User-Agent.
  2. gpt-oss / reasoning models reject response_format=json_object (HTTP
     400/403), so the client must retry prompt-only.
Both are exercised offline by stubbing urlopen."""

import io
import json
import urllib.error

import pytest

from staticpulse.llm.groq_client import GroqClient
from staticpulse.schemas.llm_outputs import ExploitabilityResult

_GOOD = json.dumps({
    "exploitability": "high", "adjusted_severity": "high",
    "adjusted_confidence": 0.8, "false_positive": False,
    "false_positive_reason": None, "reasoning": "tainted input into raw SQL",
})


def _fake_response(payload_content: str):
    body = json.dumps({
        "choices": [{"message": {"content": payload_content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }).encode("utf-8")
    return io.BytesIO(body)


def test_sends_user_agent(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["ua"] = req.get_header("User-agent")
        return _cm(_fake_response(_GOOD))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    GroqClient(api_key="x").complete(
        system="s", user="u", schema=ExploitabilityResult, prompt_version="v1")
    assert seen["ua"] and "python-urllib" not in seen["ua"].lower()


def test_falls_back_when_json_mode_rejected(monkeypatch):
    calls = {"n": 0, "had_response_format": []}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        payload = json.loads(req.data)
        calls["had_response_format"].append("response_format" in payload)
        if "response_format" in payload:                 # first attempt
            raise urllib.error.HTTPError(req.full_url, 403, "forbidden", {}, io.BytesIO(b"1010"))
        return _cm(_fake_response(_GOOD))                 # prompt-only retry

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = GroqClient(api_key="x").complete(
        system="s", user="u", schema=ExploitabilityResult, prompt_version="v1")
    assert calls["had_response_format"] == [True, False]  # tried JSON mode, then dropped it
    assert r.parsed.adjusted_confidence == 0.8


class _cm:
    """Minimal context-manager wrapper around a BytesIO for urlopen()."""
    def __init__(self, f): self.f = f
    def __enter__(self): return self.f
    def __exit__(self, *a): return False
