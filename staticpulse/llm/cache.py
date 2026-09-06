"""Content-addressed disk cache for LLM responses.

Keyed on everything that can change the answer: prompt version, model,
temperature, and a hash of the system+user text. Editing a prompt bumps its
version and so invalidates only its own entries. A cache hit means a re-push
of the same PR costs zero tokens — the single biggest cost lever on free tiers.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_DIR = ".staticpulse_cache/llm"


def _key(*, prompt_version: str, model: str, temperature: float, system: str, user: str) -> str:
    h = hashlib.sha256()
    for part in (prompt_version, model, f"{temperature:.4f}"):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    # Hash the (possibly large) prompts separately so the key stays small.
    h.update(hashlib.sha256(system.encode("utf-8")).digest())
    h.update(hashlib.sha256(user.encode("utf-8")).digest())
    return h.hexdigest()


class ResponseCache:
    """Small JSON-on-disk cache. Safe to disable for a forced-fresh run."""

    def __init__(self, root: str | Path = DEFAULT_DIR, *, enabled: bool = True) -> None:
        self.root = Path(root)
        self.enabled = enabled

    def _path(self, key: str) -> Path:
        # Shard by first two hex chars so one directory doesn't get huge.
        return self.root / key[:2] / f"{key[2:]}.json"

    def get(self, **kw: Any) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        path = self._path(_key(**kw))
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, *, value: dict[str, Any], **kw: Any) -> None:
        # Always write, even when reads are disabled — a later enabled run can
        # then reuse it. Refusing to write is rarely the intent of "no cache".
        path = self._path(_key(**kw))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)  # atomic, so a crash can't leave a half file
