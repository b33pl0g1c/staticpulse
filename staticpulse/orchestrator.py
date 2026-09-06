"""Wire the pipeline together.

  diff -> scanners -> normalize/scope -> [LLM exploitability] ->
          [LLM patches] -> apply review memory -> decide

The budget tracker and response cache are created ONCE here and threaded into
every LLM stage, so the per-PR caps mean what they say.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from staticpulse.agents.exploitability import review_findings
from staticpulse.agents.normalizer import normalize
from staticpulse.agents.patch import generate_patches
from staticpulse.llm.budget import BudgetTracker
from staticpulse.llm.cache import ResponseCache
from staticpulse.llm.factory import build_llm_client
from staticpulse.memory import ReviewMemory
from staticpulse.policy.engine import Decision, decide
from staticpulse.schemas.finding import Finding
from staticpulse.tools.git_diff import compute_diff
from staticpulse.tools.semgrep_runner import SemgrepNotFound, run_semgrep


@dataclass
class RunResult:
    decision: Decision
    findings: list[Finding]
    changed_files: list[str]
    scanner_errors: dict[str, str] = field(default_factory=dict)
    budget: dict[str, int] = field(default_factory=dict)
    llm_used: bool = False
    patches_verified: int = 0
    suppressed: int = 0


def run_pipeline(
    repo_path: str | Path,
    *,
    use_llm: bool = False,
    cache_enabled: bool = True,
    generate_patches_enabled: bool = True,
    max_patches: int = 10,
) -> RunResult:
    repo = Path(repo_path)
    diff = compute_diff(repo)

    raw: list[Finding] = []
    errors: dict[str, str] = {}

    # --- scanner layer ---
    try:
        raw.extend(run_semgrep(repo))
    except SemgrepNotFound as e:
        errors["semgrep"] = str(e)

    # --- normalize + diff-scope ---
    findings = normalize(raw, diff)

    # --- LLM stages (optional), sharing one budget + cache ---
    budget = BudgetTracker()
    llm_used = False
    patches_verified = 0
    if use_llm:
        cache = ResponseCache(enabled=cache_enabled)
        client, reason = build_llm_client(cache=cache, budget=budget)
        if client is None:
            errors["llm"] = reason or "llm unavailable"
        else:
            findings, llm_errors = review_findings(findings, client=client, repo_path=str(repo))
            llm_used = True
            if llm_errors:
                errors["exploitability"] = f"{len(llm_errors)} finding(s) errored"

            if generate_patches_enabled:
                findings, patch_errors = generate_patches(
                    findings, client=client, repo_path=str(repo), max_patches=max_patches,
                )
                patches_verified = sum(1 for f in findings if f.patch_status == "verified")
                if patch_errors:
                    errors["patch"] = f"{len(patch_errors)} finding(s) errored"

    # --- cross-push review memory: suppress previously-dismissed findings ---
    memory = ReviewMemory.load(repo)
    suppressed = 0
    if memory.dismissed:
        updated: list[Finding] = []
        for f in findings:
            if not f.false_positive and memory.is_dismissed(f.id):
                updated.append(f.model_copy(update={
                    "false_positive": True,
                    "false_positive_reason": f"previously dismissed: {memory.reason(f.id)}",
                }))
                suppressed += 1
            else:
                updated.append(f)
        findings = updated

    # --- deterministic decision (always Python) ---
    decision = decide(findings)

    return RunResult(
        decision=decision,
        findings=findings,
        changed_files=diff.changed_files,
        scanner_errors=errors,
        budget=budget.snapshot(),
        llm_used=llm_used,
        patches_verified=patches_verified,
        suppressed=suppressed,
    )
