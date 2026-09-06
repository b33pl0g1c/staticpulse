"""GitHub client — offline, with a fake request function. No network."""

from staticpulse.github import (
    MARKER, post_inline_review, post_or_update_summary, pr_context_from_env,
)


class FakeGH:
    """Records calls and returns scripted responses."""
    def __init__(self, existing_comments=None):
        self.calls = []
        self.existing = existing_comments or []
    def __call__(self, method, url, token, body=None):
        self.calls.append((method, url, body))
        if method == "GET":
            return self.existing
        return {"html_url": "https://github.com/x/y/pull/1#comment-1", "id": 42}


def test_summary_creates_when_none_exists():
    gh = FakeGH(existing_comments=[])
    url = post_or_update_summary(repo="o/r", pr_number=1, body="hi", token="t", _request_fn=gh)
    methods = [c[0] for c in gh.calls]
    assert "POST" in methods and "PATCH" not in methods
    assert url.endswith("comment-1")


def test_summary_edits_when_marker_present():
    gh = FakeGH(existing_comments=[{"id": 99, "body": f"{MARKER}\nold"}])
    post_or_update_summary(repo="o/r", pr_number=1, body="new", token="t", _request_fn=gh)
    methods = [c[0] for c in gh.calls]
    assert "PATCH" in methods and "POST" not in methods
    # the PATCH targets the existing comment id
    assert any("comments/99" in (c[1] or "") for c in gh.calls if c[0] == "PATCH")


def test_summary_skips_without_token():
    gh = FakeGH()
    assert post_or_update_summary(repo="o/r", pr_number=1, body="x", token=None, _request_fn=gh) is None
    assert gh.calls == []


def test_inline_review_posts_comments():
    gh = FakeGH()
    ok = post_inline_review(repo="o/r", pr_number=1, commit_sha="abc",
                            comments=[{"path": "a.py", "line": 3, "body": "b"}],
                            token="t", _request_fn=gh)
    assert ok is True
    method, url, body = gh.calls[-1]
    assert method == "POST" and url.endswith("/pulls/1/reviews")
    assert body["commit_id"] == "abc"
    assert body["comments"][0]["side"] == "RIGHT"


def test_inline_review_skips_without_sha_or_comments():
    gh = FakeGH()
    assert post_inline_review(repo="o/r", pr_number=1, commit_sha="", comments=[{"path":"a","line":1,"body":"b"}], token="t", _request_fn=gh) is False
    assert post_inline_review(repo="o/r", pr_number=1, commit_sha="abc", comments=[], token="t", _request_fn=gh) is False


def test_pr_context_empty_off_actions(monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    ctx = pr_context_from_env()
    assert ctx.pr_number is None and ctx.is_fork is False


def test_pr_context_detects_fork(tmp_path, monkeypatch):
    import json
    event = {"pull_request": {"number": 7, "head": {"sha": "s", "repo": {"full_name": "fork/r"}},
                              "base": {"repo": {"full_name": "orig/r"}}}}
    ep = tmp_path / "event.json"
    ep.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(ep))
    monkeypatch.setenv("GITHUB_REPOSITORY", "orig/r")
    ctx = pr_context_from_env()
    assert ctx.pr_number == 7 and ctx.head_sha == "s" and ctx.is_fork is True
