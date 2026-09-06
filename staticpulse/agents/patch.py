"""Patch agent (Phase 3, C1) — verify-by-rescan.

For each scanner finding worth fixing:
  1. Ask the LLM for replacement code for the offending lines.
  2. Reject obvious gibberish (mojibake) before doing anything with it.
  3. Copy the repo to a throwaway dir, splice the replacement into the file.
  4. Re-run the scanner on the copy.
  5. Mark `verified` only if the finding is gone; else `unverified`.

Nothing is ever applied to the real tree. A verified patch is dramatically
more credible than a raw LLM suggestion — that's the whole point.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from staticpulse.llm.base import LLMClient, LLMError
from staticpulse.llm.prompts import PATCH_SYSTEM, PATCH_USER, PATCH_VERSION
from staticpulse.schemas.finding import Finding
from staticpulse.schemas.llm_outputs import PatchSuggestion
from staticpulse.tools.rescan import rescan_semgrep
from staticpulse.utils.safe_join import safe_read_text, safe_resolve

_CONTEXT = 20
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__",
              ".staticpulse_cache", ".pytest_cache"}


def generate_patches(
    findings: list[Finding],
    *,
    client: LLMClient,
    repo_path: str,
    max_patches: int = 10,
) -> tuple[list[Finding], list[str]]:
    """Attempt a verified patch for each eligible finding. Returns
    (updated_findings, errors); order preserved."""
    out: list[Finding] = []
    errors: list[str] = []
    attempted = 0
    for f in findings:
        if not _eligible(f):
            out.append(f)
            continue
        if attempted >= max_patches:
            out.append(f.model_copy(update={"patch_status": "none",
                                            "patch_note": "patch budget reached"}))
            continue
        attempted += 1
        try:
            out.append(_patch_one(f, client=client, repo_path=repo_path))
        except LLMError as e:
            errors.append(f"{f.id}: {e}")
            out.append(f.model_copy(update={"patch_status": "none",
                                            "patch_note": f"llm error: {e}"}))
    return out, errors


def _eligible(f: Finding) -> bool:
    """Which findings get a patch attempt."""
    if f.false_positive:
        return False
    if f.source not in {"semgrep", "bandit", "sast"}:
        return False  # only scanner findings can be verified by re-running it
    if f.severity in {"info", "low"}:
        return False
    if not f.file_path or not f.start_line:
        return False
    return True


def _patch_one(f: Finding, *, client: LLMClient, repo_path: str) -> Finding:
    context = _read_context(repo_path, f)
    user = PATCH_USER.format(
        title=f.title, rule_id=f.rule_id or "-", file_path=f.file_path,
        start_line=f.start_line, end_line=f.end_line or f.start_line,
        code_context=context or "(unavailable)",
    )
    result = client.complete(
        system=PATCH_SYSTEM, user=user, schema=PatchSuggestion,
        prompt_version=PATCH_VERSION,
    )
    sug = result.parsed

    if sug.unfixable or not sug.replacement_code.strip():
        return f.model_copy(update={"patch_status": "none",
                                    "patch_note": "LLM declined to auto-patch"})
    bad = _looks_like_gibberish(sug.replacement_code)
    if bad:
        return f.model_copy(update={"patch_status": "none",
                                    "patch_note": f"rejected patch: {bad}"})

    updated = f.model_copy(update={
        "patch_replacement": sug.replacement_code,
        "patch_explanation": sug.explanation,
    })
    return _apply_and_verify(updated, repo_path)


def _apply_and_verify(f: Finding, repo_path: str) -> Finding:
    """Copy the tree, splice the replacement in, rescan the copy."""
    src = Path(repo_path).resolve()
    with tempfile.TemporaryDirectory(prefix="staticpulse-patch-") as tmp:
        dst = Path(tmp) / "tree"
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*_SKIP_DIRS))
        if not _splice(dst, f):
            return f.model_copy(update={"patch_status": "suggested",
                                        "patch_note": "could not resolve line range to apply"})
        res = rescan_semgrep(f, str(dst))
        if res.error:
            return f.model_copy(update={"patch_status": "unverified",
                                        "patch_note": f"rescan failed: {res.error}"})
        if res.finding_persists:
            return f.model_copy(update={"patch_status": "unverified",
                                        "patch_note": "scanner still reports the finding after the patch"})
        return f.model_copy(update={"patch_status": "verified",
                                    "patch_note": "scanner no longer reports the finding on the patched copy"})


def _splice(tree: Path, f: Finding) -> bool:
    """Replace lines [start, end] of the finding's file with the replacement.

    Preserves the original file's leading indentation on the first line if the
    model dropped it. Routes the read through safe_resolve so a crafted
    file_path can't escape the copied tree."""
    try:
        target = safe_resolve(tree, f.file_path)  # type: ignore[arg-type]
    except Exception:
        return False
    if not target.is_file():
        return False
    try:
        original = target.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return False

    a = max(0, (f.start_line or 1) - 1)
    b = min(len(original), f.end_line or f.start_line or 1)
    if a >= b:
        return False

    # Reuse the original first line's indentation if the model omitted it.
    lead = original[a][: len(original[a]) - len(original[a].lstrip())]
    repl_lines = (f.patch_replacement or "").rstrip("\n").splitlines() or [""]
    if lead and not repl_lines[0].startswith((" ", "\t")):
        repl_lines = [(lead + ln) if ln.strip() else ln for ln in repl_lines]
    repl = [ln + "\n" for ln in repl_lines]
    if not original[b - 1].endswith("\n"):
        repl[-1] = repl[-1].rstrip("\n")

    new = original[:a] + repl + original[b:]
    try:
        target.write_text("".join(new), encoding="utf-8")
    except OSError:
        return False
    return True


def _read_context(repo_path: str, f: Finding) -> str:
    text = safe_read_text(repo_path, f.file_path or "")
    if text is None:
        return f.evidence
    lines = text.splitlines()
    end = f.end_line or f.start_line or 1
    lo = max(0, (f.start_line or 1) - 1 - _CONTEXT)
    hi = min(len(lines), end + _CONTEXT)
    width = len(str(hi))
    rendered = []
    for i in range(lo, hi):
        mark = ">>" if (f.start_line - 1) <= i <= (end - 1) else "  "
        rendered.append(f"{mark} {str(i + 1).rjust(width)} | {lines[i]}")
    return "\n".join(rendered)


def _looks_like_gibberish(text: str) -> str | None:
    """Reject mojibake before it reaches a report. Returns a reason or None.

    Free / low-tier models occasionally emit hundreds of tokens of mojibake
    (mixed CJK, Greek, and math glyphs) instead of a patch; a cheap
    non-ASCII-ratio check catches that class cleanly without flagging normal
    code, which is overwhelmingly ASCII."""
    if not text.strip():
        return "empty replacement"
    non_ascii = sum(1 for c in text if ord(c) > 0x7F)
    if non_ascii / max(1, len(text)) > 0.15:
        return "high non-ASCII ratio (looks like mojibake)"
    return None
