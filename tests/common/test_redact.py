"""Tests for mulebox.common.redact. All tokens below are obviously fake."""

import time

import pytest

from mulebox.common import redact
from mulebox.common.redact import REPLACEMENT as R
from mulebox.common.redact import Redactor, StreamRedactor

GH_TOKEN = "ghp_" + "A1b2C3d4E5" * 4  # 44 chars, fake
FINE_GRAINED = "github_pat_" + "11FAKEFAKE0_" + "x" * 40
AWS_KEY = "AKIA" + "FAKEFAKEFAKE1234"
PEM = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAAfakefakefakefakefakefake\n"
    "fakefakefakefakefakefakefakefakefakefakefake==\n"
    "-----END OPENSSH PRIVATE KEY-----"
)


# --- Redactor: known secrets ------------------------------------------------------------


def test_known_secret_is_replaced_everywhere():
    r = Redactor(["s3cret-value"])
    assert r.redact("a s3cret-value b s3cret-value") == f"a {R} b {R}"


def test_short_and_blank_secrets_are_ignored():
    r = Redactor(["12345", "      ", ""], patterns=False)
    r.add_secret("abcde")
    assert r.redact("12345 abcde") == "12345 abcde"
    r.add_secret("abcdef")
    assert r.redact("abcdef") == R


def test_secrets_are_matched_literally():
    r = Redactor(["a.b*c+d(e)[f]$"], patterns=False)
    assert r.redact("x a.b*c+d(e)[f]$ y") == f"x {R} y"
    assert r.redact("aXbbbcdde") == "aXbbbcdde"


def test_longest_secret_wins():
    r = Redactor(["hunter22", "hunter22-extended"], patterns=False)
    assert r.redact("pw hunter22-extended!") == f"pw {R}!"
    assert r.redact("pw hunter22!") == f"pw {R}!"


def test_overlapping_secrets_leave_nothing_behind():
    r = Redactor(["abcdefgh", "efghijkl"], patterns=False)
    out = r.redact("..abcdefghijkl..")
    assert "efgh" not in out and "ijkl" not in out and out.startswith("..")


def test_patterns_can_be_disabled():
    assert Redactor(patterns=False).redact(f"token={GH_TOKEN}") == f"token={GH_TOKEN}"


# --- Redactor: built-in patterns --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"push with {GH_TOKEN} ok", f"push with {R} ok"),
        (f"gho_{'z' * 36}", R),
        (f"ghs_{'Q9' * 18}.", f"{R}."),
        (f"[{FINE_GRAINED}]", f"[{R}]"),
        (f"key {AWS_KEY} end", f"key {R} end"),
        ("Authorization: Bearer abc.def-ghi_jkl", f"Authorization: Bearer {R}"),
        ("authorization:bearer   xyz123", f"authorization:bearer   {R}"),
        ('-H "Authorization: Basic YWxpY2U6ZmFrZQ=="', f'-H "Authorization: Basic {R}"'),
        ("password=hunter2 next", f"password={R} next"),
        ("DB_PASSWORD = 'two words'", f"DB_PASSWORD = {R}"),
        ('--api-token="fake value"', f"--api-token={R}"),
        ("API_KEY=fake123&x=1", f"API_KEY={R}&x=1"),
        ("client_secret=fake;", f"client_secret={R};"),
        ('{"password": "fake pass", "user": "alice"}', f'{{"password": "{R}", "user": "alice"}}'),
        ("https://alice:fakepass@git.example.com/repo", f"https://alice:{R}@git.example.com/repo"),
        ("postgres://alice:p%40ss@192.168.1.50:5432/db", f"postgres://alice:{R}@192.168.1.50:5432/db"),
        (f"before\n{PEM}\nafter", f"before\n{R}\nafter"),
        ("-----BEGIN PRIVATE KEY-----\nMIIfake\n(no end)", R),
    ],
)
def test_builtin_patterns(text, expected):
    assert Redactor().redact(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "build passed in 12 s",
        "ghp_short",  # too short to be a token
        "https://git.example.com/alice/example-app",
        "-----BEGIN PUBLIC KEY-----",
        "password: (prompted)",
        "AKIAlowercase0000000",
    ],
)
def test_harmless_text_is_left_alone(text):
    assert Redactor().redact(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "a" * 200_000,
        "password" * 50_000,
        "token=" * 50_000,
        "a.b-" * 50_000,
        "x://" * 50_000,
        "x://u:" * 40_000,
        "Authorization: " * 20_000,
        "-----BEGIN PRIVATE KEY-----" * 5_000,
        "ghp_" * 50_000,
    ],
)
def test_long_input_stays_fast(text):
    r = Redactor(["fake-secret-1", "fake-secret-2"])
    start = time.monotonic()
    r.redact(text)
    stream = StreamRedactor(["fake-secret-1"])
    for i in range(0, len(text), 4096):
        stream.feed(text[i : i + 4096])
    stream.flush()
    assert time.monotonic() - start < 3


# --- StreamRedactor -------------------------------------------------------------------


def stream_all(redactor: StreamRedactor, chunks: list[str]) -> str:
    return "".join(redactor.feed(c) for c in chunks) + redactor.flush()


SECRET = "fake-deploy-key-42"
STREAM_TEXTS = [
    f"step 1\nusing {SECRET} now\nstep 2\n",
    f"{SECRET}{SECRET}",
    f"curl -H 'Authorization: Bearer {SECRET}xyz' https://example.com\ndone\n",
    f"export TOKEN={GH_TOKEN}\r\nnext\n",
    f"clone https://alice:fakepass@git.example.com/x\n{AWS_KEY}\n",
    f"log\n{PEM}\nlog after\n",
]


@pytest.mark.parametrize("text", STREAM_TEXTS)
def test_stream_split_at_every_position(text):
    expected = Redactor([SECRET]).redact(text)
    for i in range(len(text) + 1):
        out = stream_all(StreamRedactor([SECRET]), [text[:i], text[i:]])
        assert out == expected, f"split at {i}"
        assert SECRET not in out and GH_TOKEN not in out


@pytest.mark.parametrize("text", STREAM_TEXTS)
def test_stream_one_char_at_a_time(text):
    assert stream_all(StreamRedactor([SECRET]), list(text)) == Redactor([SECRET]).redact(text)


def test_stream_three_way_splits():
    text = f"a {SECRET} b {SECRET}\n"
    expected = Redactor([SECRET]).redact(text)
    for i in range(len(text)):
        for j in range(i, len(text) + 1):
            assert stream_all(StreamRedactor([SECRET]), [text[:i], text[i:j], text[j:]]) == expected


def test_secret_with_newline_split_anywhere():
    secret = "line-one\nline-two"
    text = f"x\n{secret}\ny\n"
    for i in range(len(text) + 1):
        out = stream_all(StreamRedactor([secret]), [text[:i], text[i:]])
        assert out == f"x\n{R}\ny\n", f"split at {i}"


def test_complete_lines_are_released_immediately():
    s = StreamRedactor([SECRET])
    assert s.feed(f"one {SECRET}\ntwo") == f"one {R}\n"
    assert s.feed("\n") == "two\n"
    assert s.flush() == ""


def test_pem_block_is_held_until_its_end_line():
    s = StreamRedactor()
    lines = (f"before\n{PEM}\nafter\n").splitlines(keepends=True)
    released = [s.feed(line) for line in lines]
    assert released[0] == "before\n"
    assert all(r == "" for r in released[1:4])  # BEGIN and body held back
    assert released[4] == f"{R}\n" and released[5] == "after\n"


def test_unterminated_pem_is_redacted_on_flush():
    s = StreamRedactor()
    assert s.feed("-----BEGIN RSA PRIVATE KEY-----\nMIIfake\n") == ""
    assert s.flush() == R


def test_oversized_unterminated_pem_is_not_held_forever(monkeypatch):
    monkeypatch.setattr(redact, "PEM_HOLD_CHARS", 100)
    s = StreamRedactor()
    assert s.feed("-----BEGIN PRIVATE KEY-----\n") == ""
    assert s.feed("A" * 200 + "\n") == R


def test_long_line_without_newline_is_released_early():
    s = StreamRedactor([SECRET])
    out = s.feed("x" * (redact.MAX_LINE_CHARS + 5000))
    assert 0 < len(out) and set(out) == {"x"}
    rest = s.feed(SECRET[:5]) + s.feed(SECRET[5:] + "y") + s.flush()
    assert SECRET not in out + rest and rest.endswith(f"{R}y")


def test_secret_added_mid_stream_is_used():
    s = StreamRedactor()
    assert s.feed("before\n") == "before\n"
    s.add_secret(SECRET)
    assert s.feed(f"now {SECRET}\n") == f"now {R}\n"


def test_flush_resets_the_stream():
    s = StreamRedactor([SECRET])
    s.feed("partial")
    assert s.flush() == "partial"
    assert s.flush() == ""
