"""Discover eval fixtures. Each fixture is a directory with `base/`, `head/`,
and `expected.yaml`. The runner turns base+head into a real git repo so the
pipeline's diff path is exercised — the whole reason this harness exists."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from staticpulse.eval.schema import Expected

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass
class Scenario:
    id: str
    path: Path          # the fixture dir (has base/, head/, expected.yaml)
    expected: Expected

    @property
    def base_dir(self) -> Path:
        return self.path / "base"

    @property
    def head_dir(self) -> Path:
        return self.path / "head"


def load_scenarios(root: Path | None = None) -> list[Scenario]:
    root = root or FIXTURES_DIR
    scenarios: list[Scenario] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        exp_file = d / "expected.yaml"
        if not exp_file.exists():
            continue
        expected = Expected.model_validate(yaml.safe_load(exp_file.read_text(encoding="utf-8")))
        scenarios.append(Scenario(id=d.name, path=d, expected=expected))
    return scenarios
