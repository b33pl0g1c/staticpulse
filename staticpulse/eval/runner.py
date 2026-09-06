"""Run the pipeline over every fixture, in one or both modes.

`scanners_only` disables the LLM (no key, no cost) and measures the
deterministic baseline. `full` enables the LLM. The delta between the two is
the whole point: it shows exactly where the LLM half changes a decision, and
at what precision / latency cost.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from staticpulse.eval.gitbuild import built_repo
from staticpulse.eval.loader import Scenario, load_scenarios
from staticpulse.eval.matcher import MatchResult, match
from staticpulse.eval.metrics import precision, recall
from staticpulse.orchestrator import run_pipeline

Mode = str  # "scanners_only" | "full"


@dataclass
class ModeRun:
    mode: Mode
    decision: str
    decision_correct: bool
    match: MatchResult
    latency_ms: int
    tokens_in: int = 0
    tokens_out: int = 0
    patches_verified: int = 0


@dataclass
class ScenarioResult:
    id: str
    expected_decision: str
    runs: dict[Mode, ModeRun] = field(default_factory=dict)


def run_scenario(sc: Scenario, *, modes: tuple[Mode, ...]) -> ScenarioResult:
    result = ScenarioResult(id=sc.id, expected_decision=sc.expected.expected_decision)
    for mode in modes:
        with built_repo(sc) as repo:
            start = time.monotonic()
            rr = run_pipeline(str(repo), use_llm=(mode == "full"))
            elapsed = int((time.monotonic() - start) * 1000)
        m = match(rr.findings, sc.expected.labels)
        result.runs[mode] = ModeRun(
            mode=mode,
            decision=rr.decision.status,
            decision_correct=(rr.decision.status == sc.expected.expected_decision),
            match=m,
            latency_ms=elapsed,
            tokens_in=rr.budget.get("tokens_in", 0),
            tokens_out=rr.budget.get("tokens_out", 0),
            patches_verified=rr.patches_verified,
        )
    return result


def run_corpus(*, modes: tuple[Mode, ...], scenarios: list[Scenario] | None = None) -> list[ScenarioResult]:
    scenarios = scenarios or load_scenarios()
    return [run_scenario(sc, modes=modes) for sc in scenarios]


@dataclass
class Aggregate:
    mode: Mode
    scenarios: int
    decisions_correct: int
    tp: int
    fp: int
    fn: int
    tokens_in: int
    tokens_out: int
    avg_latency_ms: int

    @property
    def recall(self) -> float:
        return recall(self.tp, self.fn)

    @property
    def precision(self) -> float:
        return precision(self.tp, self.fp)


def aggregate(results: list[ScenarioResult], mode: Mode) -> Aggregate:
    runs = [r.runs[mode] for r in results if mode in r.runs]
    n = len(runs)
    return Aggregate(
        mode=mode,
        scenarios=n,
        decisions_correct=sum(1 for r in runs if r.decision_correct),
        tp=sum(r.match.tp for r in runs),
        fp=sum(r.match.fp for r in runs),
        fn=sum(r.match.fn for r in runs),
        tokens_in=sum(r.tokens_in for r in runs),
        tokens_out=sum(r.tokens_out for r in runs),
        avg_latency_ms=int(sum(r.latency_ms for r in runs) / n) if n else 0,
    )
