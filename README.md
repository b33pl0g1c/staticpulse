# StaticPulse

**Blends static analysis with real-time, continuous evaluation.**

StaticPulse is an AI-assisted pull-request security reviewer. It runs on a PR,
looks at what changed, and returns a single verdict a CI job can gate on —
`PASS` / `WARN` / `FAIL`. A deterministic Semgrep pipeline finds the
pattern-matchable bugs; an LLM layer continuously evaluates each finding's
exploitability and proposes fixes it *verifies* by re-scanning; and a
plain-Python policy engine always makes the final call. It pairs with my
`agentic-pentester` project (the dynamic/active half).

> Status: **Phases 0–5 built.** Deterministic core, LLM layer, differentiators
> (verified patches, review memory, pentester bridge), an evaluation harness, and a
> GitHub Actions integration with inline PR comments — all shipped and unit-tested.
> Live end-to-end verification runs on the first real pull request.

## The one idea that matters

The LLM is **only ever advisory**. A plain-Python policy engine (`staticpulse/policy/engine.py`)
makes the final `PASS` / `WARN` / `FAIL` call. That keeps the CI gate reproducible, auditable,
and working even when every LLM provider is down.

## Pipeline

```
git diff -> scanners (Semgrep) -> normalize + diff-scope
         -> [LLM exploitability] -> [LLM verified patches]
         -> review memory -> policy decision
```

- **diff-scope** — findings on files/lines the PR didn't touch are dropped, so the bot never
  blames the author for the repo's existing backlog.
- **safe_join** — every file read routes through one path-traversal-safe helper
  (`staticpulse/utils/safe_join.py`), so a crafted or LLM-derived `file_path` can't escape
  the repo root.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
pip install semgrep             # see Windows note below

staticpulse scan --repo <path> --no-llm --output report.json
```

Exit codes: `0` PASS/WARN, `1` FAIL, `2` error.

### Turning on the LLM layer

Copy `.env.example` to `.env` and add a free Groq key
(<https://console.groq.com/keys>):

```bash
GROQ_API_KEY=gsk_...
```

Then drop `--no-llm`. Each finding gets an exploitability second opinion that
can lower severity/confidence or mark a false positive — but **never** downgrades
a critical secret (a Python invariant, not left to the model). Responses are
cached under `.staticpulse_cache/`, so re-running the same scan costs **zero
tokens**, and a single per-PR budget tracker caps calls and tokens across every
LLM stage.

Without a key the pipeline still runs, scanners-only, and notes the gap.

### Windows note

Recent Semgrep (1.176+) runs natively on Windows and is verified here — the SQLi fixture
scans to a `FAIL`, the clean fixture to a `PASS`. `staticpulse` invokes the `semgrep`
executable installed alongside the interpreter, so you don't need to activate the venv.
If Semgrep is ever missing, the tool still runs: it reports the gap and returns a
deterministic decision on whatever findings it has.

Dependency note: modern Semgrep pulls Click 8.4, which needs Typer >= 0.15 (older Typer
0.12 breaks) — worth knowing if you ever pin an older Semgrep.

## Tests

```bash
pytest -q
```

64 tests cover the path guard, the LLM cache + budget, verify-by-rescan, review memory,
the normalizer's dedup + diff-scope, the eval harness, the GitHub client + PR rendering, and the policy engine. The security
control (`safe_join`) was tested before anything was built on it.

## The differentiators

- **Verify-by-rescan patches.** With the LLM on, each scanner finding gets a
  proposed fix. The fix is spliced into a *throwaway copy* of the tree and
  Semgrep re-runs; it is marked `verified` only if the finding disappears.
  Nothing is ever applied to your real tree. Verified live: the model returns
  `cursor.execute("... id = ?", (user_id,))` and the rescan confirms it.

- **Cross-push false-positive memory.** `staticpulse dismiss <finding_id>`
  records a reviewer's verdict keyed on the finding's stable content-hash ID;
  later scans suppress it. `staticpulse restore <finding_id>` undoes it — so the
  bot stops re-flagging an issue a human already triaged.

- **Pentester bridge.** `staticpulse handoff --target <url>` writes a JSON file of
  *dynamically-confirmable* findings (SQLi, SSRF, authz gaps — things a DAST can
  hit) with a probe hint for each, so the sibling `agentic-pentester` can confirm
  a static hypothesis by actually calling the app. The pentester runs only against
  a target you own — invocation is a deliberate manual step, never triggered
  automatically.

## GitHub Actions

Drop-in workflow at `.github/workflows/staticpulse.yml`. On every pull request it
scans the diff, posts a **summary comment** (edited in place on re-push, never
spammed) plus **inline review comments** on each finding's line — verified fixes
render as one-click `suggestion` blocks — and sets the CI status: a `FAIL`
decision exits non-zero and blocks the merge.

Setup: add a `GROQ_API_KEY` repository secret to enable the LLM layer. Without
it, StaticPulse still runs scanners-only and posts the deterministic result.

### One-click: use it as a GitHub Action

Others can add StaticPulse to any repo in ~5 lines — no Python or Semgrep setup:

```yaml
# .github/workflows/security.yml
name: Security review
on: { pull_request: { types: [opened, synchronize, reopened] } }
permissions: { contents: read, pull-requests: write, issues: write }
jobs:
  staticpulse:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }        # full history so the diff is meaningful
      - uses: b33pl0g1c/staticpulse@v1
        with:
          groq-api-key: ${{ secrets.GROQ_API_KEY }}   # optional; omit for scanners-only
```

### Run it anywhere with Docker

Semgrep and StaticPulse are baked into one image, so it runs on any host
(Windows included) with nothing else installed:

```bash
docker run --rm -v "$PWD:/src" ghcr.io/b33pl0g1c/staticpulse scan --repo /src --no-llm
```

Add `-e GROQ_API_KEY=...` to enable the LLM layer. The image is published to the
GitHub Container Registry on every push to `main`.

### Least-privilege permissions

The bundled workflow (and the action) request only what they use:

```yaml
permissions:
  contents: read          # read the code to scan it
  pull-requests: write    # post the review + inline comments
  issues: write           # the summary comment goes through the issues API
```

**Fork PRs:** GitHub gives `pull_request` runs from forks a read-only token and
no secrets. StaticPulse detects this, skips posting, and still sets the status —
it never errors on a fork PR. (This is a real limitation of the `pull_request`
trigger, stated plainly rather than left silent.)

## Evaluation

Fixtures live in `staticpulse/eval/fixtures/` as `base/` + `head/` trees. The
harness builds a **real two-commit git repo** from each and runs the pipeline
against `HEAD~1...HEAD`, so the diff-scoping and changed-line filters are
genuinely exercised rather than skipped on a static directory.

```bash
staticpulse eval run                 # scanners-only, offline, no key
staticpulse eval run --llm           # add full (LLM) mode
staticpulse eval run --update-readme # refresh the table below from the JSON
```

Latest aggregate (regenerated by the command, never hand-edited):

<!-- EVAL:START -->

*Generated by `staticpulse eval run` — do not hand-edit.*

| Metric | scanners_only | full |
|---|---|---|
| decisions correct | 5/6 | 5/6 |
| recall | 0.80 | 0.80 |
| precision | 0.80 | 0.80 |
| true positives | 4 | 4 |
| false positives | 1 | 1 |
| false negatives | 1 | 1 |
| patches verified | 0 | 3 |
| avg latency | 10.6s | 18.7s |
| LLM tokens (in/out) | 0/0 | 3515/3316 |

<!-- EVAL:END -->

An honest reading: on this corpus the LLM half doesn't change the decision or
recall — its value is the 3 **verified** patches, at a latency and token cost.
The one scanners-only miss is `missing_authz`: a semantic authorization bug no
pattern scanner can see. There is no discovery agent yet, so it's missed in both
modes — the eval quantifies exactly that recall ceiling, which motivates adding
an AI-discovery agent as a future phase.

## Roadmap

- An AI-discovery agent to close the semantic-bug recall ceiling the eval
  surfaces (e.g. the `missing_authz` case).
- More scanners and languages; a richer normalizer (co-located-finding collapse).
