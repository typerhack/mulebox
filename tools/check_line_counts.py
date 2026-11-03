"""Enforce the file-size rule from AGENTS.md.

Code files should stay at or under WARN_LINES lines; a file with FAIL_LINES or more is
never accepted. Docs are exempt. Run directly (`python tools/check_line_counts.py`) or
through the test suite (tests/test_line_counts.py).
"""

import sys
from pathlib import Path

WARN_LINES = 300
FAIL_LINES = 500
CODE_SUFFIXES = {".py", ".sh", ".js", ".ts", ".css", ".html", ".toml", ".yml", ".yaml"}
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "build", "dist", "node_modules"}
REPO_ROOT = Path(__file__).resolve().parent.parent


def code_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in path.parts):
            continue
        if path.is_file() and path.suffix in CODE_SUFFIXES:
            files.append(path)
    return sorted(files)


def count_lines(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def check(root: Path = REPO_ROOT) -> tuple[list[str], list[str]]:
    """Return (warnings, failures) as printable lines."""
    warnings, failures = [], []
    for path in code_files(root):
        lines = count_lines(path)
        name = path.relative_to(root)
        if lines >= FAIL_LINES:
            failures.append(f"{name}: {lines} lines (limit: under {FAIL_LINES}; split it)")
        elif lines > WARN_LINES:
            warnings.append(f"{name}: {lines} lines (aim: {WARN_LINES} or fewer)")
    return warnings, failures


def main() -> int:
    warnings, failures = check()
    for line in warnings:
        print(f"warning: {line}")
    for line in failures:
        print(f"error: {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
