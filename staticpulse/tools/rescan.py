"""Re-scan a patched copy of the tree to verify a fix.

The whole point of Phase 3: a patch is only credible if the scanner that
raised the finding stops raising it after the fix is applied. Matching is
deliberately fuzzy — a patch shifts line numbers and can change the exact
rule that fires — so we treat the finding as "still present" if any result
lands in the same file, on the same rule family, within a few lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from staticpulse.schemas.finding import Finding
from staticpulse.tools.semgrep_runner import SemgrepNotFound, run_semgrep

_LINE_TOLERANCE = 5


@dataclass
class RescanResult:
    finding_persists: bool
    error: str | None = None


def _norm(p: str | None) -> str:
    return str(PurePosixPath((p or "").replace("\\", "/").lstrip("./"))).lower()


def rescan_semgrep(finding: Finding, patched_root: str) -> RescanResult:
    """Re-run Semgrep on `patched_root` and report if `finding` still shows."""
    try:
        results = run_semgrep(patched_root)
    except SemgrepNotFound as e:
        return RescanResult(finding_persists=True, error=str(e))
    except Exception as e:  # noqa: BLE001 — any scanner failure is inconclusive
        return RescanResult(finding_persists=True, error=f"{type(e).__name__}: {e}")

    return RescanResult(finding_persists=_still_present(finding, results))


def _still_present(orig: Finding, results: list[Finding]) -> bool:
    of = _norm(orig.file_path)
    oline = orig.start_line or 0
    # Compare on rule_id when we have it; otherwise fall back to file+line.
    orule = (orig.rule_id or "").lower()
    for r in results:
        if _norm(r.file_path) != of:
            continue
        if orule and (r.rule_id or "").lower() != orule:
            continue
        rline = r.start_line or 0
        if abs(rline - oline) <= _LINE_TOLERANCE:
            return True
    return False
