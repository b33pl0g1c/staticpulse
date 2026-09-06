"""The cache must key on prompt version + model + inputs, and survive a
round-trip. No network involved."""

from staticpulse.llm.cache import ResponseCache


def _kw(**over):
    base = dict(prompt_version="v1", model="m", temperature=0.1, system="sys", user="usr")
    base.update(over)
    return base


def test_put_then_get(tmp_path):
    c = ResponseCache(tmp_path, enabled=True)
    c.put(value={"parsed": {"x": 1}}, **_kw())
    assert c.get(**_kw()) == {"parsed": {"x": 1}}


def test_miss_on_different_user(tmp_path):
    c = ResponseCache(tmp_path, enabled=True)
    c.put(value={"parsed": {"x": 1}}, **_kw())
    assert c.get(**_kw(user="other")) is None


def test_version_bump_invalidates(tmp_path):
    c = ResponseCache(tmp_path, enabled=True)
    c.put(value={"parsed": {"x": 1}}, **_kw(prompt_version="v1"))
    assert c.get(**_kw(prompt_version="v2")) is None


def test_disabled_reads_return_none(tmp_path):
    c = ResponseCache(tmp_path, enabled=False)
    c.put(value={"parsed": {"x": 1}}, **_kw())   # still writes
    assert c.get(**_kw()) is None
