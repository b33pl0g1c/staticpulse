"""staticpulse CLI.

    staticpulse scan --repo . --output report.json
    staticpulse scan --repo . --no-llm

Exit codes (so a CI job's status reflects the gate):
    0  PASS or WARN
    1  FAIL
    2  terminal error
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from staticpulse.orchestrator import run_pipeline

app = typer.Typer(
    name="staticpulse",
    add_completion=False,
    no_args_is_help=True,
    help="An AI-assisted PR security reviewer (deterministic core).",
)

from staticpulse.eval.cli import app as eval_app  # noqa: E402
app.add_typer(eval_app, name="eval")

_EXIT = {"PASS": 0, "WARN": 0, "FAIL": 1}



def _force_utf8() -> None:
    """Windows consoles default to cp1252, which crashes on non-latin
    output (scanner messages, unicode identifiers). Reconfigure to UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def _load_env() -> None:
    """Load .env from the cwd so a local GROQ_API_KEY is picked up."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

@app.callback()
def _root() -> None:
    """AI-assisted PR security reviewer."""
    _force_utf8()
    _load_env()


@app.command()
def scan(
    repo: Path = typer.Option(Path("."), "--repo", "-r", help="Repository root to scan."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write JSON report here."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Deterministic only (no API key needed)."),
) -> None:
    try:
        result = run_pipeline(repo, use_llm=not no_llm)
    except Exception as e:  # noqa: BLE001 — top-level guard maps to exit 2
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    d = result.decision
    color = {"PASS": typer.colors.GREEN, "WARN": typer.colors.YELLOW, "FAIL": typer.colors.RED}[d.status]
    typer.secho(f"\n{d.status}  (risk {d.risk_score}/100)", fg=color, bold=True)
    typer.echo(f"{len(result.findings)} finding(s) in {len(result.changed_files)} changed file(s)")
    for r in d.reasons[:20]:
        typer.echo(f"  - {r}")
    if result.llm_used:
        b = result.budget
        typer.echo(
            f"LLM: {b.get('llm_calls', 0)} call(s), "
            f"{b.get('tokens_in', 0)}+{b.get('tokens_out', 0)} tokens"
        )
        verified = [f for f in result.findings if f.patch_status == "verified"]
        if verified:
            typer.secho(f"Verified patches: {len(verified)}", fg=typer.colors.GREEN)
            for f in verified[:10]:
                typer.echo(f"  [verified] {f.title[:60]}")
    if result.suppressed:
        typer.echo(f"Suppressed (previously dismissed): {result.suppressed}")
    for comp, err in result.scanner_errors.items():
        typer.secho(f"  ! {comp}: {err}", fg=typer.colors.YELLOW)

    if output:
        report = {
            "decision": d.to_dict(),
            "findings": [f.model_dump() for f in result.findings],
            "changed_files": result.changed_files,
            "scanner_errors": result.scanner_errors,
        }
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        typer.echo(f"\nwrote {output}")

    raise typer.Exit(code=_EXIT.get(d.status, 2))


@app.command()
def dismiss(
    finding_id: str = typer.Argument(..., help="Finding id to suppress on future runs."),
    reason: str = typer.Option("dismissed by reviewer", "--reason"),
    repo: Path = typer.Option(Path("."), "--repo", "-r"),
) -> None:
    """Remember that a finding is a false positive; it won't fail future runs."""
    from staticpulse.memory import ReviewMemory
    mem = ReviewMemory.load(repo)
    mem.dismiss(finding_id, reason)
    typer.secho(f"dismissed {finding_id}: {reason}", fg=typer.colors.YELLOW)


@app.command()
def restore(
    finding_id: str = typer.Argument(..., help="Finding id to un-dismiss."),
    repo: Path = typer.Option(Path("."), "--repo", "-r"),
) -> None:
    """Undo a previous dismiss."""
    from staticpulse.memory import ReviewMemory
    mem = ReviewMemory.load(repo)
    ok = mem.restore(finding_id)
    typer.echo(f"restored {finding_id}" if ok else f"{finding_id} was not dismissed")


@app.command()
def handoff(
    repo: Path = typer.Option(Path("."), "--repo", "-r"),
    target: str = typer.Option(..., "--target", help="URL of the locally-running app, e.g. http://127.0.0.1:5000"),
    out: Path = typer.Option(Path("handoff.json"), "--out", "-o"),
    no_llm: bool = typer.Option(False, "--no-llm"),
) -> None:
    """Emit a handoff file of dynamically-confirmable findings for agentic-pentester."""
    from staticpulse.bridge import write_handoff
    result = run_pipeline(repo, use_llm=not no_llm)
    n = write_handoff(result.findings, target=target, out_path=out)
    typer.echo(f"wrote {out} with {n} candidate(s) for dynamic confirmation against {target}")


@app.command("scan-pr")
def scan_pr(
    repo: Path = typer.Option(Path("."), "--repo", "-r"),
    output: Path = typer.Option(Path("report.json"), "--output", "-o"),
    no_llm: bool = typer.Option(False, "--no-llm"),
    inline: bool = typer.Option(True, "--inline/--no-inline",
                                help="Post inline review comments on each finding's line."),
) -> None:
    """CI entry point: scan, write a report, and post results to the PR.

    Reads PR metadata and GITHUB_TOKEN from the Actions environment. Degrades
    gracefully off-Actions, on fork PRs (read-only token), or with no token:
    it still scans and still sets the exit code, it just skips posting.
    """
    import json as _json
    import os as _os

    from staticpulse.github import (
        post_inline_review, post_or_update_summary, pr_context_from_env,
    )
    from staticpulse.report_md import build_inline_comments, render_summary

    try:
        result = run_pipeline(repo, use_llm=not no_llm)
    except Exception as e:  # noqa: BLE001
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    d = result.decision
    report = {
        "decision": d.to_dict(),
        "findings": [f.model_dump() for f in result.findings],
        "changed_files": result.changed_files,
        "scanner_errors": result.scanner_errors,
    }
    output.write_text(_json.dumps(report, indent=2), encoding="utf-8")

    ctx = pr_context_from_env()
    token = _os.environ.get("GITHUB_TOKEN")
    posted = None
    if ctx.repo and ctx.pr_number and token and not ctx.is_fork:
        posted = post_or_update_summary(
            repo=ctx.repo, pr_number=ctx.pr_number,
            body=render_summary(result), token=token,
        )
        if inline and ctx.head_sha:
            comments = build_inline_comments(result.findings)
            if comments:
                post_inline_review(
                    repo=ctx.repo, pr_number=ctx.pr_number, commit_sha=ctx.head_sha,
                    comments=comments, token=token,
                )
    elif ctx.is_fork:
        typer.echo("fork PR: no secrets/write token available — skipping PR comment")
    else:
        typer.echo("no PR context or token — skipping PR comment (report written)")

    color = {"PASS": typer.colors.GREEN, "WARN": typer.colors.YELLOW, "FAIL": typer.colors.RED}[d.status]
    typer.secho(f"{d.status} (risk {d.risk_score}/100)", fg=color, bold=True)
    if posted:
        typer.echo(f"posted: {posted}")
    raise typer.Exit(code=_EXIT.get(d.status, 2))


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(app())  # pragma: no cover
