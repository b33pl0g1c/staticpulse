"""Test the path-traversal guard FIRST — it's a security control, so it earns
a test before anything is built on top of it."""

from pathlib import Path

import pytest

from staticpulse.utils.safe_join import (
    PathEscapeError,
    safe_read_text,
    safe_resolve,
)


def test_normal_path_resolves(tmp_path: Path):
    (tmp_path / "app.py").write_text("print('hi')", encoding="utf-8")
    resolved = safe_resolve(tmp_path, "app.py")
    assert resolved == (tmp_path / "app.py").resolve()


def test_traversal_is_rejected(tmp_path: Path):
    with pytest.raises(PathEscapeError):
        safe_resolve(tmp_path, "../../etc/passwd")


def test_absolute_path_is_rejected(tmp_path: Path):
    # An absolute path outside the repo must not resolve inside it.
    outside = "/etc/passwd" if Path("/etc").exists() else "C:/Windows/system.ini"
    with pytest.raises(PathEscapeError):
        safe_resolve(tmp_path, outside)


def test_read_returns_none_on_escape(tmp_path: Path):
    assert safe_read_text(tmp_path, "../secret.txt") is None


def test_read_returns_none_when_too_big(tmp_path: Path):
    big = tmp_path / "big.txt"
    big.write_text("x" * 2000, encoding="utf-8")
    assert safe_read_text(tmp_path, "big.txt", max_bytes=1000) is None


def test_read_returns_content(tmp_path: Path):
    (tmp_path / "ok.txt").write_text("hello", encoding="utf-8")
    assert safe_read_text(tmp_path, "ok.txt") == "hello"
