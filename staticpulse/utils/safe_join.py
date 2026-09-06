r"""safe_join — the one path-traversal-safe file reader.

A PR reviewer opens many files whose paths come from scanners, diffs, and even
LLM output — some of it ultimately derived from attacker-controlled PR content.
A bare `Path(repo_path) / file_path` join lets `../../etc/passwd` (or an
absolute path) escape the repo root, and that guard is easy to forget in one
reader out of many. So every file read in this project routes through this
single helper, where the check lives exactly once.
"""

from __future__ import annotations

from pathlib import Path


class PathEscapeError(ValueError):
    """Raised when a resolved path would fall outside the repo root."""


def safe_resolve(repo_root: str | Path, rel_path: str) -> Path:
    """Resolve `rel_path` under `repo_root`, refusing anything that escapes.

    Handles the two escape shapes that matter:
      - traversal:  "../../etc/passwd"
      - absolute:   "/etc/passwd" or "C:/Windows/..."  (Path join drops the
                    root on POSIX but not always on Windows, so we check.)

    Returns the resolved absolute Path. Raises PathEscapeError on escape.
    """
    root = Path(repo_root).resolve()
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as e:
        raise PathEscapeError(
            f"path {rel_path!r} escapes repo root {root}"
        ) from e
    return candidate


def safe_read_text(
    repo_root: str | Path,
    rel_path: str,
    *,
    max_bytes: int = 1_000_000,
) -> str | None:
    """Read a repo file safely. Returns None on any problem (missing, too big,
    escapes root, unreadable) — callers degrade gracefully rather than crash.

    `max_bytes` is a DoS guard: a crafted PR could point at a multi-hundred-MB
    lockfile the LLM has no business ingesting.
    """
    try:
        path = safe_resolve(repo_root, rel_path)
    except PathEscapeError:
        return None
    if not path.is_file():
        return None
    try:
        if path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
