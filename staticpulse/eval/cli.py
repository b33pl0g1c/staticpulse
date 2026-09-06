"""`staticpulse eval run` — run the corpus and write reports."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="Evaluation harness.", no_args_is_help=True)


@app.command()
def run(
    llm: bool = typer.Option(False, "--llm", help="Also run full (LLM) mode; needs an API key."),
    md: Path = typer.Option(Path("reports/eval.md"), "--md", help="Markdown report path."),
    json_out: Path = typer.Option(Path("reports/eval.json"), "--json", help="JSON report path."),
    update_readme: bool = typer.Option(False, "--update-readme", help="Inject the table into README between EVAL markers."),
) -> None:
    """Run every fixture in scanners-only (and optionally full) mode."""
    from staticpulse.eval.report import inject_readme, write_reports
    from staticpulse.eval.runner import aggregate, run_corpus

    modes = ("scanners_only", "full") if llm else ("scanners_only",)
    typer.echo(f"running {', '.join(modes)} ...")
    results = run_corpus(modes=modes)

    md.parent.mkdir(parents=True, exist_ok=True)
    write_reports(results, modes, md_path=md, json_path=json_out)

    for m in modes:
        a = aggregate(results, m)
        typer.echo(
            f"{m}: {a.decisions_correct}/{a.scenarios} decisions correct, "
            f"recall {a.recall:.2f}, precision {a.precision:.2f}"
        )
    if update_readme and inject_readme(results, modes, readme=Path("README.md")):
        typer.echo("README table updated")
    typer.echo(f"wrote {md} and {json_out}")
