import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_line_counts", REPO_ROOT / "tools" / "check_line_counts.py"
)
check_line_counts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_line_counts)


def _write_lines(path: Path, count: int) -> None:
    path.write_text("x = 1\n" * count, encoding="utf-8")


def test_repository_has_no_oversized_files():
    _, failures = check_line_counts.check(REPO_ROOT)
    assert failures == []


def test_limits(tmp_path):
    _write_lines(tmp_path / "small.py", 300)
    _write_lines(tmp_path / "large.py", 301)
    _write_lines(tmp_path / "huge.py", 500)
    (tmp_path / "notes.md").write_text("line\n" * 900, encoding="utf-8")
    warnings, failures = check_line_counts.check(tmp_path)
    assert [w.split(":")[0] for w in warnings] == ["large.py"]
    assert [f.split(":")[0] for f in failures] == ["huge.py"]


def test_skips_virtualenv(tmp_path):
    (tmp_path / ".venv").mkdir()
    _write_lines(tmp_path / ".venv" / "big.py", 900)
    assert check_line_counts.check(tmp_path) == ([], [])


def test_skips_top_level_docs_only(tmp_path):
    (tmp_path / "docs").mkdir()
    _write_lines(tmp_path / "docs" / "specimen.html", 900)
    (tmp_path / "pkg" / "docs").mkdir(parents=True)
    _write_lines(tmp_path / "pkg" / "docs" / "big.py", 500)
    _, failures = check_line_counts.check(tmp_path)
    assert [f.split(":")[0] for f in failures] == [str(Path("pkg") / "docs" / "big.py")]
