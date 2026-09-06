from staticpulse.agents.normalizer import normalize
from staticpulse.schemas.finding import Finding
from staticpulse.tools.git_diff import DiffResult


def _f(fid, path, line):
    return Finding(id=fid, source="semgrep", title="t", file_path=path, start_line=line)


def test_dedup_by_id():
    out = normalize([_f("a", "x.py", 1), _f("a", "x.py", 1)], DiffResult(changed_files=[]))
    assert len(out) == 1


def test_out_of_scope_file_dropped():
    diff = DiffResult(changed_files=["touched.py"])
    out = normalize([_f("a", "untouched.py", 5)], diff)
    assert out == []


def test_off_diff_line_dropped():
    diff = DiffResult(changed_files=["app.py"], changed_line_ranges={"app.py": [(10, 12)]})
    out = normalize([_f("a", "app.py", 100)], diff)
    assert out == []


def test_in_scope_line_kept():
    diff = DiffResult(changed_files=["app.py"], changed_line_ranges={"app.py": [(10, 12)]})
    out = normalize([_f("a", "app.py", 11)], diff)
    assert len(out) == 1
