import pytest

from mulebox.common.anonymize import Anonymizer


@pytest.mark.parametrize("text, gone", [
    ("cannot open /home/alice/work/app/server.ts", "alice"),
    ("cannot open /Users/alice/work/app", "alice"),
    ("connect to 192.168.1.50:5432 failed", "192.168.1.50"),
    ("mail alice@example.com please", "alice@example.com"),
    ("ssh alice@build-1 refused", "alice@build-1"),
    ("clone https://github.com/example-org/example-app.git", "example-org"),
    ("wlan cc:b1:82:00:00:04 dropped", "cc:b1:82:00:00:04"),
    ("postgres://app:hunter22222@db.example.com/x", "hunter22222"),
    ("API_TOKEN=abcdefghijklmnop", "abcdefghijklmnop"),
])
def test_identifying_text_is_removed_without_being_told(text, gone):
    assert gone not in Anonymizer().scrub(text)


@pytest.mark.parametrize("text", ["example-app failed", "EXAMPLE-APP failed",
                                  "in example-app/src/a.ts", "example-app_ci database",
                                  "the example-app-test job"])
def test_known_names_go_in_any_case_and_inside_longer_words(text):
    assert "example-app" not in Anonymizer(["example-app"]).scrub(text).lower()


def test_longest_name_wins_so_no_fragment_is_left():
    scrubbed = Anonymizer(["alice", "alice-desktop"]).scrub("on alice-desktop")
    assert scrubbed == "on [private]"


def test_common_and_tiny_names_are_not_treated_as_private():
    text = "main check failed on a branch"
    assert Anonymizer(["main", "check", "a", "MULEBOX"]).scrub(text) == text


def test_ordinary_technical_text_survives():
    text = "mulebox 0.11.1 exit 124 on Python 3.13.1 in src/a.ts:12"
    assert Anonymizer().scrub(text) == text


@pytest.mark.parametrize("text", [
    "see https://example.com/a and /home/alice/x from 10.0.0.1, bob@example.com",
    "password=abc123456 and token: x", "[private] [url] [address] ~/x [redacted] [email]",
])
def test_scrubbing_twice_changes_nothing(text):
    """`feedback post` relies on this: a clean draft must stay exactly the same."""
    anonymizer = Anonymizer(["alice", "private"])
    once = anonymizer.scrub(text)
    assert anonymizer.scrub(once) == once
