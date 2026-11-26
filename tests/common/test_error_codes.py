"""One table of error codes (common/error_codes.py): every code the code names is in it, and
docs/agents.md lists exactly its rows."""

import re
from pathlib import Path

from mulebox.common import error_codes

ROOT = Path(__file__).resolve().parents[2]
# `error_code="x"`, `error_code = "x"` and a kind's code beside its exit (`report.EXIT_X, "x"`)
NAMED = re.compile(r'(?:error_code\s*=\s*|EXIT_[A-Z_]+, )"([a-z]+\.[a-z_]+)"')


def test_codes_are_dotted_words_with_a_fix():
    for code in error_codes.CODES.values():
        assert re.fullmatch(r"[a-z]+\.[a-z_]+", code.name), code.name
        assert code.fix.strip() and code.meaning.strip()
        assert code.exit in (1, 2, 3, 4, 5)


def test_every_code_in_the_code_is_in_the_table():
    named = set()
    for path in (ROOT / "mulebox").rglob("*.py"):
        if path.name == "error_codes.py":
            continue
        for match in NAMED.finditer(path.read_text()):
            named.add(match.group(1))
    assert named, "the pattern found no code at all"
    assert named <= set(error_codes.CODES), named - set(error_codes.CODES)


def test_wire_codes_map_to_known_codes():
    assert set(error_codes.FROM_WIRE.values()) <= set(error_codes.CODES)


def test_agents_md_lists_the_table():
    text = (ROOT / "docs" / "agents.md").read_text()
    rows = re.findall(r"^\| `([a-z_.]+)` \| (\d) \| ", text, re.M)
    assert rows == [(c.name, str(c.exit)) for c in error_codes.CODES.values()]


def test_an_unknown_code_gets_the_internal_fix():
    assert error_codes.fix_for("no.such") == error_codes.CODES["mulebox.internal"].fix
