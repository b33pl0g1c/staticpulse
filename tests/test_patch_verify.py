"""Verify-by-rescan (C1) end to end, WITHOUT an LLM.

A fake client returns a known-good parameterized-query fix; the agent applies
it to a throwaway copy and lets REAL Semgrep confirm the finding is gone. This
proves the apply->rescan loop independent of any model. Skips if semgrep isn't
installed."""

import shutil

import pytest

from staticpulse.agents.patch import generate_patches
from staticpulse.llm.base import LLMClient, LLMResult
from staticpulse.schemas.finding import Finding
from staticpulse.schemas.llm_outputs import PatchSuggestion
from staticpulse.tools.semgrep_runner import _semgrep_exe

pytestmark = pytest.mark.skipif(_semgrep_exe() is None, reason="semgrep not installed")


class FixClient(LLMClient):
    def __init__(self, replacement): self.replacement = replacement
    def complete(self, **kw):
        return LLMResult[PatchSuggestion](parsed=PatchSuggestion(
            replacement_code=self.replacement, explanation="parameterized"))


def _vuln_repo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "app.py").write_text(
        "import sqlite3\n"
        "def get_user(conn, user_id):\n"
        "    cursor = conn.cursor()\n"
        '    query = "SELECT * FROM users WHERE id = \'%s\'" % user_id\n'
        "    cursor.execute(query)\n"
        "    return cursor.fetchone()\n",
        encoding="utf-8")
    return d


def test_good_fix_verifies(tmp_path):
    repo = _vuln_repo(tmp_path)
    from staticpulse.tools.semgrep_runner import run_semgrep
    findings = run_semgrep(repo)
    assert findings, "semgrep should flag the SQLi"

    # A genuinely safe rewrite of the offending line(s).
    fix = 'cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))'
    out, errs = generate_patches(findings, client=FixClient(fix), repo_path=str(repo))
    assert errs == []
    patched = [f for f in out if f.patch_status == "verified"]
    assert patched, "a correct fix should verify by rescan"
    # The real tree is untouched — nothing is auto-applied.
    assert "% user_id" in (repo / "app.py").read_text(encoding="utf-8")


def test_unverified_when_finding_persists(tmp_path, monkeypatch):
    """If the scanner still reports the finding after the patch, status is
    unverified. Stub the rescan so this stays fast (no second semgrep run)."""
    from staticpulse.agents import patch as patch_mod
    from staticpulse.tools.rescan import RescanResult

    repo = _vuln_repo(tmp_path)
    f = Finding(id="1", source="semgrep", rule_id="python.sqli.formatted-sql-query",
                title="SQLi", severity="high", confidence=0.7,
                file_path="app.py", start_line=4, end_line=4)
    monkeypatch.setattr(patch_mod, "rescan_semgrep",
                        lambda finding, root: RescanResult(finding_persists=True))
    out, _ = generate_patches([f], client=FixClient("query = something(user_id)"),
                              repo_path=str(repo))
    assert out[0].patch_status == "unverified"
