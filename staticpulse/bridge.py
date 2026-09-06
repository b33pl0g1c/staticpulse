"""Bridge to the dynamic pentester (Phase 3, C5) — the seam.

The static reviewer produces *hypotheses* ("this endpoint may lack an authz
check"). The sibling `agentic-pentester` project can *confirm* them by actually
calling a locally-running instance. This module selects the findings worth
handing over and writes a handoff file the pentester can consume.

The selection logic is real and tested here. The actual invocation of the
pentester is a documented integration point (`dispatch`) — it needs a running
target, so it stays a thin, explicit call rather than hidden magic.
"""

from __future__ import annotations

import json
from pathlib import Path

from staticpulse.schemas.finding import Finding

# Vulnerability classes a black-box DAST can realistically confirm by sending
# requests: things that manifest at an HTTP endpoint. Crypto-at-rest or a
# hardcoded secret can't be confirmed by calling the app, so they're excluded.
_DYNAMICALLY_CONFIRMABLE = (
    "sqli", "sql-injection", "sql injection",
    "ssrf", "path-traversal", "path traversal",
    "open-redirect", "xss", "command-injection", "command injection",
    "idor", "auth", "authz", "authorization", "access control",
)


def selectable(f: Finding) -> bool:
    """True if a finding is worth dynamic confirmation."""
    if f.false_positive:
        return False
    if f.severity in {"info", "low"}:
        return False
    text = f"{f.rule_id or ''} {f.title}".lower()
    return any(k in text for k in _DYNAMICALLY_CONFIRMABLE)


def build_handoff(findings: list[Finding], *, target: str) -> dict:
    """Build the handoff payload the pentester consumes."""
    items = [
        {
            "finding_id": f.id,
            "title": f.title,
            "file": f.file_path,
            "line": f.start_line,
            "hypothesis": f.title,
            "suggested_probe": _probe_hint(f),
        }
        for f in findings if selectable(f)
    ]
    return {"target": target, "count": len(items), "candidates": items}


def _probe_hint(f: Finding) -> str:
    t = f"{f.rule_id or ''} {f.title}".lower()
    if "sql" in t:
        return "send a crafted parameter (e.g. ' OR '1'='1) and look for a data/error leak"
    if "ssrf" in t:
        return "point the request at an internal address and check the response"
    if "auth" in t or "idor" in t or "access" in t:
        return "call the endpoint without / with a lower-privilege token"
    if "redirect" in t:
        return "supply an external URL and check for an off-site redirect"
    return "exercise the endpoint with adversarial input"


def write_handoff(findings: list[Finding], *, target: str, out_path: str | Path) -> int:
    """Write the handoff JSON. Returns the number of candidates."""
    payload = build_handoff(findings, target=target)
    Path(out_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload["count"]


# --- integration point (needs a running target; not invoked automatically) ---
def dispatch(handoff_path: str) -> None:  # pragma: no cover
    """Hand the file to agentic-pentester. Left as an explicit integration
    point: the pentester runs against a locally-hosted target the operator
    controls, so wiring it is a deliberate, authorized step — not something
    the reviewer should trigger on its own."""
    raise NotImplementedError(
        "Run the pentester manually against the handoff file: it targets a "
        "live app and must only be pointed at systems you own."
    )
