"""The mojibake guard rejects bad patches before they reach a report."""

from staticpulse.agents.patch import _looks_like_gibberish


def test_normal_code_passes():
    assert _looks_like_gibberish('cursor.execute("SELECT * FROM t WHERE id = ?", (uid,))') is None


def test_empty_rejected():
    assert _looks_like_gibberish("   ") is not None


def test_mojibake_rejected():
    assert _looks_like_gibberish("δ§ 你好 ∑∫ ‱ 世界 μμμ ♜♞ ") is not None
