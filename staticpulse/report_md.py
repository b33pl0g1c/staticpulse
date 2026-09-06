"""Render StaticPulse results for a PR: a summary comment and inline comments.

Kept separate from the GitHub client so the rendering is pure (easy to test)
and the client stays about HTTP.
"""

from __future__ import annotations

from staticpulse.orchestrator import RunResult
from staticpulse.schemas.finding import Finding

_EMOJI = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}
_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def render_summary(result: RunResult) -> str:
    """The single Markdown body for the PR summary comment."""
    d = result.decision
    lines = [
        f"## {_EMOJI.get(d.status, '')} StaticPulse — {d.status}",
        "",
        f"**Risk score:** {d.risk_score}/100 · "
        f"**{len(result.findings)} finding(s)** across {len(result.changed_files)} changed file(s)",
        "",
    ]

    active = [f for f in result.findings if not f.false_positive]
    if active:
        lines.append("| Severity | Finding | Location | Patch |")
        lines.append("|---|---|---|---|")
        for f in sorted(active, key=lambda x: _SEV_ORDER.get(x.severity, 9)):
            loc = f"`{f.file_path}:{f.start_line}`" if f.file_path else "—"
            patch = {"verified": "✔ verified", "unverified": "proposed",
                     "suggested": "suggested"}.get(f.patch_status, "—")
            title = (f.title[:70] + "…") if len(f.title) > 70 else f.title
            lines.append(f"| {f.severity} | {title} | {loc} | {patch} |")
        lines.append("")

    verified = [f for f in active if f.patch_status == "verified"]
    if verified:
        lines.append(f"### {len(verified)} verified fix(es)")
        lines.append("A fix was applied to a throwaway copy and the scanner no "
                     "longer reports the issue. Review before applying — nothing "
                     "is auto-committed.")
        for f in verified:
            if f.patch_replacement:
                lines += ["", f"**{f.file_path}:{f.start_line}** — {f.patch_explanation or ''}",
                          "```suggestion", f.patch_replacement.rstrip("\n"), "```"]
        lines.append("")

    suppressed = result.suppressed
    if suppressed:
        lines.append(f"_{suppressed} finding(s) suppressed by a prior reviewer dismissal._")
        lines.append("")

    if result.scanner_errors:
        lines.append("<details><summary>Notes</summary>\n")
        for comp, err in result.scanner_errors.items():
            lines.append(f"- `{comp}`: {err}")
        lines.append("\n</details>")

    lines.append("")
    lines.append("<sub>StaticPulse · deterministic gate, LLM-advised. Re-runs edit this comment.</sub>")
    return "\n".join(lines)


def build_inline_comments(findings: list[Finding]) -> list[dict]:
    """One inline comment per non-FP finding that has a location.

    Findings are already diff-scoped, so their lines fall inside the PR's
    changed ranges — a requirement for the GitHub review API to accept them.
    """
    out: list[dict] = []
    for f in findings:
        if f.false_positive or not f.file_path or not f.start_line:
            continue
        body = f"**{f.severity.upper()}: {f.title}**"
        if f.rule_id:
            body += f"\n\n`{f.rule_id}`"
        if f.patch_status == "verified" and f.patch_replacement:
            body += ("\n\nVerified fix (scanner-confirmed on a throwaway copy):\n"
                     f"```suggestion\n{f.patch_replacement.rstrip(chr(10))}\n```")
        elif f.recommendation if hasattr(f, "recommendation") else False:
            body += f"\n\n{f.recommendation}"
        out.append({"path": f.file_path, "line": f.start_line, "body": body})
    return out
