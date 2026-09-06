"""Cross-push review memory (Phase 3, C4).

Most PR bots re-flag the same finding on every push because they keep no state
between runs. Because our finding IDs are stable (content-hashed), a reviewer
can dismiss a finding once and have it stay suppressed on later runs of the
same PR.

Stored as a small JSON file at the repo root. Not secret — safe to commit if a
team wants shared suppressions, or gitignore for per-clone ones.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

STORE_NAME = ".staticpulse_memory.json"


@dataclass
class ReviewMemory:
    path: Path
    dismissed: dict[str, str]   # finding_id -> reason

    @classmethod
    def load(cls, repo_path: str | Path) -> "ReviewMemory":
        path = Path(repo_path) / STORE_NAME
        dismissed: dict[str, str] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                dismissed = {str(k): str(v) for k, v in (data.get("dismissed") or {}).items()}
            except (OSError, json.JSONDecodeError, AttributeError):
                dismissed = {}
        return cls(path=path, dismissed=dismissed)

    def is_dismissed(self, finding_id: str) -> bool:
        return finding_id in self.dismissed

    def reason(self, finding_id: str) -> str:
        return self.dismissed.get(finding_id, "")

    def dismiss(self, finding_id: str, reason: str = "dismissed by reviewer") -> None:
        self.dismissed[finding_id] = reason
        self._save()

    def restore(self, finding_id: str) -> bool:
        if finding_id in self.dismissed:
            del self.dismissed[finding_id]
            self._save()
            return True
        return False

    def _save(self) -> None:
        self.path.write_text(
            json.dumps({"dismissed": self.dismissed}, indent=2), encoding="utf-8"
        )
