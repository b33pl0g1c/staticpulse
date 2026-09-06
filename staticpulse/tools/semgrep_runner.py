"""Run Semgrep and convert its JSON output into our Finding schema.

Semgrep is chosen as the first scanner because it's pip-installable (no
separate binary to download), multi-language, and its `--config auto` ruleset
covers the common injection/crypto/deserialization classes out of the box.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from staticpulse.schemas.finding import Finding, Severity
from staticpulse.schemas.ids import compute_finding_id

# Semgrep's rule severity (ERROR/WARNING/INFO) reflects the rule author's
# confidence, not the bug's blast radius. It's a coarse signal but fine as a
# starting map; the policy engine refines FAIL/WARN using rule keywords too.
_SEV_MAP: dict[str, Severity] = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}


class SemgrepNotFound(RuntimeError):
    """semgrep is not installed / not on PATH."""


def _semgrep_exe() -> str | None:
    """Locate the semgrep executable.

    Prefer the one installed alongside the running interpreter (the venv's
    Scripts/ or bin/ dir) so we don't depend on the caller having activated
    the venv. Fall back to PATH.
    """
    import shutil
    from pathlib import Path

    bindir = Path(sys.executable).parent
    for name in ("semgrep.exe", "semgrep"):
        cand = bindir / name
        if cand.exists():
            return str(cand)
    return shutil.which("semgrep")



def run_semgrep(repo_path: str | Path, *, config: str = "auto") -> list[Finding]:
    """Scan `repo_path` with Semgrep. Returns a list of Findings.

    Raises SemgrepNotFound if the tool is missing so the caller can degrade
    (report the gap) instead of crashing the whole run.
    """
    exe = _semgrep_exe()
    if exe is None:
        raise SemgrepNotFound("semgrep not found - `pip install semgrep`")

    proc = subprocess.run(
        [exe, "scan", "--config", config, "--json", "--quiet", str(repo_path)],
        capture_output=True,
        text=True,
        # Semgrep exits 1 when it finds results; that's success for us.
        check=False,
    )
    if not proc.stdout.strip():
        return []

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []

    findings: list[Finding] = []
    for r in data.get("results", []):
        findings.append(_result_to_finding(r, repo_path))
    return findings


def _result_to_finding(r: dict, repo_path: str | Path) -> Finding:
    extra = r.get("extra", {})
    meta = extra.get("metadata", {})
    rule_id = r.get("check_id")
    start = (r.get("start") or {}).get("line")
    end = (r.get("end") or {}).get("line") or start

    # Prefer the rule's declared impact when present; else map from severity.
    impact = (meta.get("impact") or "").upper()
    severity: Severity = {
        "CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low",
    }.get(impact, _SEV_MAP.get(extra.get("severity", "WARNING"), "medium"))

    # Path relative to the scanned root, forward-slash normalized.
    raw_path = r.get("path") or ""
    try:
        file_path = str(Path(raw_path).resolve().relative_to(Path(repo_path).resolve())).replace("\\", "/")
    except (ValueError, OSError):
        file_path = raw_path.replace("\\", "/")

    title = (meta.get("shortDescription") or extra.get("message") or rule_id or "Semgrep finding").strip()
    cwe = meta.get("cwe") or []
    if isinstance(cwe, str):
        cwe = [cwe]

    fid = compute_finding_id(
        source="semgrep", rule_id=rule_id, file_path=file_path,
        start_line=start, title=title,
    )
    return Finding(
        id=fid,
        source="semgrep",
        severity=severity,
        confidence=0.5,
        title=title[:200],
        description=extra.get("message", "")[:1000],
        file_path=file_path,
        start_line=start,
        end_line=end,
        rule_id=rule_id,
        cwe=[c for c in cwe if isinstance(c, str)],
        evidence=(extra.get("lines") or "")[:2000],
    )
