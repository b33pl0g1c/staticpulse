"""Minimal GitHub API client (standard library only).

Posts StaticPulse's results back to a pull request in two ways:
  - one summary comment, edited in place on re-push (found by a hidden marker
    so re-runs never spam new comments), and
  - inline review comments on the exact diff line of each finding.

Every request sends an explicit User-Agent — GitHub rejects requests without
one — and a missing/again read-only token makes the call skip gracefully
rather than crash, which is exactly what happens on pull requests from forks.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

MARKER = "<!-- staticpulse:bot-comment -->"
_API = "https://api.github.com"


@dataclass
class PRContext:
    repo: str | None            # "owner/name"
    pr_number: int | None
    head_sha: str | None
    is_fork: bool = False


def pr_context_from_env() -> PRContext:
    """Read PR metadata from the GitHub Actions environment. Empty off-Actions."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not os.path.exists(event_path):
        return PRContext(repo=repo, pr_number=None, head_sha=None)
    try:
        event = json.loads(open(event_path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        return PRContext(repo=repo, pr_number=None, head_sha=None)
    pr = event.get("pull_request") or {}
    head = pr.get("head") or {}
    head_repo = head.get("repo") or {}
    base_repo = (pr.get("base") or {}).get("repo") or {}
    is_fork = bool(head_repo.get("full_name") and base_repo.get("full_name")
                   and head_repo["full_name"] != base_repo["full_name"])
    return PRContext(
        repo=repo,
        pr_number=pr.get("number"),
        head_sha=head.get("sha"),
        is_fork=is_fork,
    )


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict | list:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "staticpulse")   # GitHub 403s without a UA
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_or_update_summary(
    *, repo: str, pr_number: int, body: str, token: str | None,
    _request_fn=_request,
) -> str | None:
    """Create the StaticPulse summary comment, or edit the existing one.

    Returns the comment's html_url, or None if nothing was posted (no token).
    """
    if not token:
        return None
    marked = f"{MARKER}\n{body}"
    list_url = f"{_API}/repos/{repo}/issues/{pr_number}/comments"
    try:
        comments = _request_fn("GET", list_url, token)
    except urllib.error.HTTPError:
        return None
    existing_id = None
    if isinstance(comments, list):
        for c in comments:
            if isinstance(c, dict) and MARKER in (c.get("body") or ""):
                existing_id = c.get("id")
                break
    try:
        if existing_id is not None:
            r = _request_fn("PATCH", f"{_API}/repos/{repo}/issues/comments/{existing_id}",
                            token, {"body": marked})
        else:
            r = _request_fn("POST", list_url, token, {"body": marked})
    except urllib.error.HTTPError:
        return None
    return r.get("html_url") if isinstance(r, dict) else None


def post_inline_review(
    *, repo: str, pr_number: int, commit_sha: str,
    comments: list[dict], token: str | None,
    _request_fn=_request,
) -> bool:
    """Post inline review comments in one review. `comments` are
    {path, line, body}. Returns True if a review was created."""
    if not token or not comments or not commit_sha:
        return False
    payload = {
        "commit_id": commit_sha,
        "event": "COMMENT",
        "comments": [
            {"path": c["path"], "line": c["line"], "side": "RIGHT", "body": c["body"]}
            for c in comments
        ],
    }
    try:
        _request_fn("POST", f"{_API}/repos/{repo}/pulls/{pr_number}/reviews", token, payload)
    except urllib.error.HTTPError:
        return False
    return True
