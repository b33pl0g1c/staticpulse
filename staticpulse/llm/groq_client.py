"""Groq client (OpenAI-compatible chat completions).

Groq is the default because it has a genuinely free tier and the user already
has a key from the sibling `agentic-pentester` project. The HTTP shape is the
OpenAI chat-completions API, so swapping to another OpenAI-compatible provider
later is a base-URL change.

Wraps a shared cache and budget: a cache hit costs zero tokens and doesn't
touch the budget; a live call is recorded against the budget. Retries once on
a schema-validation failure (models occasionally emit trailing prose), then
raises so the finding keeps its pre-LLM values.
"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from staticpulse.llm.base import (
    LLMClient,
    LLMError,
    LLMRateLimited,
    LLMResult,
    LLMValidationError,
)
from staticpulse.llm.budget import BudgetTracker
from staticpulse.llm.cache import ResponseCache

T = TypeVar("T", bound=BaseModel)


class _JsonModeRejected(Exception):
    """Internal: the model refused response_format=json_object."""


_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqClient(LLMClient):
    name = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "openai/gpt-oss-20b",
        cache: ResponseCache | None = None,
        budget: BudgetTracker | None = None,
    ) -> None:
        if not api_key:
            raise LLMError("GROQ_API_KEY is empty")
        self._api_key = api_key
        self.model = model
        self._cache = cache
        self._budget = budget
        # Some Groq models (the gpt-oss / reasoning family) reject
        # response_format=json_object. We probe once, then remember.
        self._json_mode = True

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        prompt_version: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> LLMResult[T]:
        ckw = dict(
            prompt_version=prompt_version, model=self.model,
            temperature=temperature, system=system, user=user,
        )
        # --- cache first: free, and doesn't consume budget ---
        if self._cache is not None:
            hit = self._cache.get(**ckw)
            if hit is not None:
                try:
                    return LLMResult[schema](
                        parsed=schema.model_validate(hit["parsed"]),
                        tokens_in=hit.get("tokens_in", 0),
                        tokens_out=hit.get("tokens_out", 0),
                        cache_hit=True,
                    )
                except (KeyError, ValidationError):
                    pass  # stale/corrupt entry — fall through to a live call

        # --- budget gate ---
        if self._budget is not None and not self._budget.can_proceed():
            raise LLMError(self._budget.skipped_reason or "budget exceeded")

        raw, tin, tout = self._call(system, user, temperature, max_tokens)
        if self._budget is not None:
            self._budget.record(tokens_in=tin, tokens_out=tout)

        parsed = self._parse(raw, schema)
        if parsed is None:
            # One corrective retry, nudging harder for bare JSON.
            raw2, tin2, tout2 = self._call(
                system, user + "\n\nReturn ONLY the JSON object. No prose.",
                temperature, max_tokens,
            )
            if self._budget is not None:
                self._budget.record(tokens_in=tin2, tokens_out=tout2)
            tin += tin2
            tout += tout2
            parsed = self._parse(raw2, schema)
            if parsed is None:
                raise LLMValidationError(f"{self.model} did not return valid {schema.__name__}")

        if self._cache is not None:
            self._cache.put(
                value={"parsed": parsed.model_dump(), "tokens_in": tin, "tokens_out": tout},
                **ckw,
            )
        return LLMResult[schema](parsed=parsed, tokens_in=tin, tokens_out=tout, cache_hit=False)

    # ---------------------------------------------------------------- internals

    def _call(self, system: str, user: str, temperature: float, max_tokens: int) -> tuple[str, int, int]:
        """One HTTP round-trip. Returns (content, tokens_in, tokens_out).

        Tries json_object mode first; if the model rejects it (HTTP 400/403),
        drops that flag and retries prompt-only. The prompt already demands a
        bare JSON object and `_parse` is tolerant, so prompt-only is fine.
        """
        try:
            return self._post(system, user, temperature, max_tokens, json_mode=self._json_mode)
        except _JsonModeRejected:
            self._json_mode = False  # remember for the rest of this run
            return self._post(system, user, temperature, max_tokens, json_mode=False)

    def _post(self, system, user, temperature, max_tokens, *, json_mode: bool) -> tuple[str, int, int]:
        import urllib.error
        import urllib.request

        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(_GROQ_URL, data=json.dumps(payload).encode("utf-8"), method="POST")
        req.add_header("Authorization", f"Bearer {self._api_key}")
        req.add_header("Content-Type", "application/json")
        # Cloudflare blocks the default "Python-urllib" UA with error 1010.
        req.add_header("User-Agent", "staticpulse/0.0.1")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if json_mode and e.code in (400, 403):
                # Likely "response_format not supported for this model".
                raise _JsonModeRejected() from e
            if e.code in (429, 413, 503):
                raise LLMRateLimited(f"groq HTTP {e.code}") from e
            raise LLMError(f"groq HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise LLMError(f"groq call failed: {e}") from e

        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        usage = data.get("usage") or {}
        return content, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))

    @staticmethod
    def _parse(raw: str, schema: type[T]) -> T | None:
        raw = raw.strip()
        if not raw:
            return None
        # Strip an accidental ```json fence if the model added one.
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.find("{"):]
        try:
            return schema.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError):
            return None
