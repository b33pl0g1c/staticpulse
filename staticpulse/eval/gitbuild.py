"""Build a real, throwaway git repo from a fixture's base/ and head/ trees.

Fixtures are stored as a `base/` tree and a `head/` tree and assembled into a
two-commit repo at runtime. That is what makes the diff-scoping and
changed-line filters testable: a fixture that is just a static directory has no
git history, so `git diff HEAD~1...HEAD` produces nothing and those filters
never run. Committing base then head gives the pipeline a genuine change to
diff, exactly like a real PR.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from staticpulse.eval.loader import Scenario


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def _copy_tree_contents(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


@contextmanager
def built_repo(scenario: Scenario) -> Iterator[Path]:
    """Yield a path to a git repo whose HEAD~1..HEAD is base -> head."""
    with tempfile.TemporaryDirectory(prefix=f"staticpulse-eval-{scenario.id}-") as tmp:
        repo = Path(tmp)
        _git(repo, "init", "-q")
        # Local identity so commits work without global git config.
        _git(repo, "config", "user.email", "eval@staticpulse.local")
        _git(repo, "config", "user.name", "staticpulse-eval")
        _git(repo, "config", "commit.gpgsign", "false")

        # Commit the base tree (may be empty for a new-file scenario).
        _copy_tree_contents(scenario.base_dir, repo)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "--allow-empty", "-m", "base")

        # Overwrite with the head tree and commit — this is the "PR".
        for item in repo.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        _copy_tree_contents(scenario.head_dir, repo)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "--allow-empty", "-m", "head")

        yield repo
