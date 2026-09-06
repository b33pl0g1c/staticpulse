"""Compute what a PR actually changed: changed files + changed line ranges.

Diff-scoping is one of the highest-value features (it's what stops the bot
blaming the author for the whole repo's backlog), so the diff path is built to
be real and exercised by the eval harness.

Modes:
  - GitHub Actions: diff `origin/<base>...HEAD`.
  - Local with history: diff `HEAD~1...HEAD`.
  - No git / no history: fall back to whole-tree, empty diff (scope filter
    then becomes a no-op, which is the safe default).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiffResult:
    changed_files: list[str]
    # file -> list of (start_line, end_line) ranges in the head version
    changed_line_ranges: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    fallback_used: bool = False


def _is_git_repo(repo: Path) -> bool:
    return (repo / ".git").exists()


def _run_git(repo: Path, args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _diff_range(repo: Path) -> str | None:
    """Pick the right git revision range for the current environment."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        base = os.environ.get("GITHUB_BASE_REF")
        if base:
            return f"origin/{base}...HEAD"
    # Local: use HEAD~1 if it exists.
    if _run_git(repo, ["rev-parse", "HEAD~1"]) is not None:
        return "HEAD~1...HEAD"
    return None


# Matches a unified-diff hunk header: @@ -old +new,count @@
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def compute_diff(repo_path: str | Path) -> DiffResult:
    repo = Path(repo_path).resolve()
    if not _is_git_repo(repo):
        return DiffResult(changed_files=_walk(repo), fallback_used=True)

    rng = _diff_range(repo)
    if rng is None:
        return DiffResult(changed_files=_walk(repo), fallback_used=True)

    names = _run_git(repo, ["diff", "--name-only", rng])
    patch = _run_git(repo, ["diff", "--unified=0", rng])
    if names is None or patch is None:
        return DiffResult(changed_files=_walk(repo), fallback_used=True)

    changed = [ln.strip().replace("\\", "/") for ln in names.splitlines() if ln.strip()]
    return DiffResult(
        changed_files=changed,
        changed_line_ranges=_parse_ranges(patch),
    )


def _parse_ranges(patch: str) -> dict[str, list[tuple[int, int]]]:
    """Extract per-file changed line ranges from a unified diff."""
    ranges: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            current = line[len("+++ b/"):].strip().replace("\\", "/")
            ranges.setdefault(current, [])
        elif line.startswith("@@") and current is not None:
            m = _HUNK.match(line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                if count == 0:  # pure deletion — nothing added to review
                    continue
                ranges[current].append((start, start + count - 1))
    return {f: r for f, r in ranges.items() if r}


def _walk(repo: Path) -> list[str]:
    """List tracked-ish files when there's no diff to work from."""
    skip = {".git", "node_modules", ".venv", "__pycache__",
            ".staticpulse_cache", ".pytest_cache"}
    skip_files = {".staticpulse_memory.json"}
    out: list[str] = []
    for p in repo.rglob("*"):
        if not p.is_file() or p.name in skip_files:
            continue
        if any(part in skip or part.startswith(".") for part in p.relative_to(repo).parts[:-1]):
            continue
        out.append(str(p.relative_to(repo)).replace("\\", "/"))
    return out
