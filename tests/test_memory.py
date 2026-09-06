"""Cross-push false-positive memory (C4)."""

from staticpulse.memory import ReviewMemory


def test_dismiss_persists(tmp_path):
    m = ReviewMemory.load(tmp_path)
    m.dismiss("abc123", "test file, not real")
    # reload from disk — a later run is a fresh process
    m2 = ReviewMemory.load(tmp_path)
    assert m2.is_dismissed("abc123")
    assert "not real" in m2.reason("abc123")


def test_restore(tmp_path):
    m = ReviewMemory.load(tmp_path)
    m.dismiss("abc123")
    assert m.restore("abc123") is True
    assert ReviewMemory.load(tmp_path).is_dismissed("abc123") is False


def test_missing_store_is_empty(tmp_path):
    assert ReviewMemory.load(tmp_path).dismissed == {}
