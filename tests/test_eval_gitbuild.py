"""The builder must produce a real 2-commit git repo whose diff is base->head."""

import shutil

import pytest

from staticpulse.eval.gitbuild import built_repo
from staticpulse.eval.loader import load_scenarios
from staticpulse.tools.git_diff import compute_diff

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def test_diff_reflects_head_change():
    sc = next(s for s in load_scenarios() if s.id == "sqli")
    with built_repo(sc) as repo:
        assert (repo / ".git").exists()
        diff = compute_diff(repo)
        assert "db.py" in diff.changed_files
        # the vulnerable line range is present (this is the whole point)
        assert diff.changed_line_ranges.get("db.py")


def test_all_fixtures_build():
    for sc in load_scenarios():
        with built_repo(sc) as repo:
            assert (repo / ".git").exists()
