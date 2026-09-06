from staticpulse.llm.budget import BudgetTracker


def test_records_accumulate():
    b = BudgetTracker()
    b.record(tokens_in=10, tokens_out=5)
    b.record(tokens_in=1, tokens_out=2)
    assert b.snapshot() == {"tokens_in": 11, "tokens_out": 7, "llm_calls": 2}


def test_stops_at_call_cap():
    b = BudgetTracker(max_llm_calls=1)
    b.record(tokens_in=1, tokens_out=1)
    assert b.can_proceed() is False
    assert "max_llm_calls" in b.skipped_reason


def test_stops_at_token_cap():
    b = BudgetTracker(max_tokens=5)
    b.record(tokens_in=3, tokens_out=3)
    assert b.can_proceed() is False
