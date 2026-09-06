"""The deterministic policy engine — the most important design choice.

The LLM is only ever advisory. THIS function, plain Python with no model call,
decides PASS / WARN / FAIL. That means the gate is reproducible, auditable, and
still works when every LLM provider is down.

v1 rules (kept intentionally small; grow later):
  - a critical secret            -> FAIL
  - a high-impact SAST pattern    -> FAIL  (SQLi, cmd-injection, deser, ...)
  - any other medium+ finding     -> WARN
"""

from __future__ import annotations

from dataclasses import dataclass, field

from staticpulse.schemas.finding import Finding

# Bug classes that are FAIL-worthy by industry consensus, regardless of how
# timid the scanner's own severity is. Matched as substrings against rule_id
# and title. A curated set of the bug classes that are FAIL-worthy by consensus.
# NOTE: matching keywords against a scanner's rule_id/title is brittle — the
# same bug class is named differently across rulesets (Semgrep's SQLi rules
# say "formatted-sql-query" / "sqlalchemy-execute-raw-query", not "sqli").
# We match BOTH hyphen and space forms, and cover the real Semgrep names.
# A cleaner long-term signal is a taint-source check (a Phase 2 refinement).
_HIGH_IMPACT = (
    # SQL injection — cover Semgrep's actual rule names + generic forms
    "sqli", "sql-injection", "sql injection", "sql_injection", "tainted-sql",
    "formatted-sql", "sql-query", "raw-query", "sql-string",
    # Command / code injection
    "command-injection", "command injection", "shell-injection",
    "os-command", "dangerous-system-call", "dangerous-subprocess",
    "shell=true", "shell-equals-true", "shell-true", "subprocess-shell",
    "code-injection", "rce", "eval-detected",
    # Deserialization
    "deserial", "pickle", "unsafe-yaml", "yaml-load", "yaml.load",
    # XML / XXE
    "xxe", "external-entity", "xml-external",
    # SSRF
    "ssrf", "server-side-request",
    # Path traversal
    "path-traversal", "path traversal", "directory-traversal",
    # Auth
    "jwt-none", "alg-none", "verify=false", "verify-false",
)

_SEV_SCORE = {"critical": 40, "high": 25, "medium": 12, "low": 5, "info": 1}


@dataclass
class Decision:
    status: str                              # PASS | WARN | FAIL
    risk_score: int                          # 0..100
    reasons: list[str] = field(default_factory=list)
    finding_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "risk_score": self.risk_score,
            "reasons": self.reasons,
            "finding_ids": self.finding_ids,
        }


def _is_high_impact(f: Finding) -> bool:
    text = f"{f.rule_id or ''}|{f.title}".lower()
    return any(k in text for k in _HIGH_IMPACT)


def _risk(findings: list[Finding]) -> int:
    total = sum(_SEV_SCORE.get(f.severity, 1) for f in findings if not f.false_positive)
    return min(100, total)


def decide(findings: list[Finding], *, min_warn_confidence: float = 0.5) -> Decision:
    reasons: list[str] = []
    contributing: list[str] = []
    fail = False
    warn = False

    for f in findings:
        if f.false_positive:
            continue

        # Critical secret -> FAIL, and never gets talked down.
        if f.source == "gitleaks" and f.severity == "critical":
            fail = True
            reasons.append(f"Critical secret: {f.title}")
            contributing.append(f.id)
            continue

        # High-impact SAST pattern at reasonable confidence -> FAIL.
        if f.source in {"semgrep", "bandit", "sast"} and _is_high_impact(f) \
                and f.confidence >= 0.5 and f.severity != "info":
            fail = True
            reasons.append(f"High-impact pattern: {f.title}")
            contributing.append(f.id)
            continue

        # Everything else medium+ -> WARN.
        if f.severity in {"medium", "high", "critical"} and f.confidence >= min_warn_confidence:
            warn = True
            reasons.append(f"Needs review: {f.title}")
            contributing.append(f.id)

    status = "FAIL" if fail else "WARN" if warn else "PASS"
    return Decision(status=status, risk_score=_risk(findings), reasons=reasons, finding_ids=contributing)
