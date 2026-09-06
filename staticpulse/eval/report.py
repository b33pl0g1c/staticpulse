"""Render eval results to JSON + Markdown, and (optionally) inject the
aggregate table into the README between markers — so the docs can never drift
from the measured numbers, so the documented table can never drift from the
JSON the harness actually produced."""

from __future__ import annotations

import json
from pathlib import Path

from staticpulse.eval.runner import Aggregate, ScenarioResult, aggregate

README_START = "<!-- EVAL:START -->"
README_END = "<!-- EVAL:END -->"


def to_json(results: list[ScenarioResult], modes: tuple[str, ...]) -> dict:
    return {
        "aggregate": {m: _agg_dict(aggregate(results, m)) for m in modes},
        "scenarios": [
            {
                "id": r.id,
                "expected": r.expected_decision,
                "runs": {
                    m: {
                        "decision": run.decision,
                        "correct": run.decision_correct,
                        "tp": run.match.tp, "fp": run.match.fp, "fn": run.match.fn,
                        "latency_ms": run.latency_ms,
                        "tokens_in": run.tokens_in, "tokens_out": run.tokens_out,
                        "patches_verified": run.patches_verified,
                    }
                    for m, run in r.runs.items()
                },
            }
            for r in results
        ],
    }


def _agg_dict(a: Aggregate) -> dict:
    return {
        "scenarios": a.scenarios,
        "decisions_correct": a.decisions_correct,
        "recall": round(a.recall, 2),
        "precision": round(a.precision, 2),
        "tp": a.tp, "fp": a.fp, "fn": a.fn,
        "tokens_in": a.tokens_in, "tokens_out": a.tokens_out,
        "avg_latency_ms": a.avg_latency_ms,
    }


def aggregate_table(results: list[ScenarioResult], modes: tuple[str, ...]) -> str:
    aggs = {m: aggregate(results, m) for m in modes}
    header = "| Metric | " + " | ".join(modes) + " |"
    sep = "|" + "---|" * (len(modes) + 1)
    rows = [
        ("decisions correct", lambda a: f"{a.decisions_correct}/{a.scenarios}"),
        ("recall", lambda a: f"{a.recall:.2f}"),
        ("precision", lambda a: f"{a.precision:.2f}"),
        ("true positives", lambda a: str(a.tp)),
        ("false positives", lambda a: str(a.fp)),
        ("false negatives", lambda a: str(a.fn)),
        ("patches verified", lambda a: str(sum(r.runs[a.mode].patches_verified for r in results if a.mode in r.runs))),
        ("avg latency", lambda a: f"{a.avg_latency_ms/1000:.1f}s"),
        ("LLM tokens (in/out)", lambda a: f"{a.tokens_in}/{a.tokens_out}"),
    ]
    lines = [header, sep]
    for name, fn in rows:
        lines.append(f"| {name} | " + " | ".join(fn(aggs[m]) for m in modes) + " |")
    return "\n".join(lines)


def to_markdown(results: list[ScenarioResult], modes: tuple[str, ...]) -> str:
    out = ["# staticpulse — Evaluation Report", "", "## Aggregate", "",
           aggregate_table(results, modes), "", "## Per-scenario", ""]
    out.append("| Scenario | Expected | " + " | ".join(modes) + " |")
    out.append("|" + "---|" * (len(modes) + 2))
    for r in results:
        cells = []
        for m in modes:
            run = r.runs.get(m)
            if not run:
                cells.append("-")
                continue
            mark = "OK" if run.decision_correct else "X"
            cells.append(f"{run.decision} {mark}")
        out.append(f"| {r.id} | {r.expected_decision} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def write_reports(results, modes, *, md_path: Path, json_path: Path) -> None:
    json_path.write_text(json.dumps(to_json(results, modes), indent=2), encoding="utf-8")
    md_path.write_text(to_markdown(results, modes), encoding="utf-8")


def inject_readme(results, modes, *, readme: Path) -> bool:
    """Replace the block between EVAL markers with a fresh aggregate table."""
    if not readme.exists():
        return False
    text = readme.read_text(encoding="utf-8")
    if README_START not in text or README_END not in text:
        return False
    table = aggregate_table(results, modes)
    pre = text.split(README_START)[0]
    post = text.split(README_END)[1]
    readme.write_text(f"{pre}{README_START}\n\n{table}\n\n{README_END}{post}", encoding="utf-8")
    return True
