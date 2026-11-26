"""The worker's last word in a job that could not start: code and fix (common/start_note.py)."""

from mulebox.common import error_codes, start_note
from mulebox.common.status import FIX_NOTE, NOT_STARTED_NOTE
from mulebox.worker.toolchains import ToolchainError


def test_an_error_gives_its_class_code_and_the_codes_fix():
    text = start_note.lines(ToolchainError("node 99 does not exist"))
    assert text == (f"{NOT_STARTED_NOTE} [toolchain.failed] node 99 does not exist\n"
                    f"{FIX_NOTE} {error_codes.fix_for('toolchain.failed')}\n")


def test_a_reason_takes_the_code_given_and_an_unknown_error_the_default():
    assert "[install.failed] it failed" in start_note.lines("it failed", "install.failed")
    assert f"[{start_note.DEFAULT}] disk full" in start_note.lines(OSError("disk full"))


def test_a_closer_fix_wins():
    text = start_note.lines(ToolchainError("x", fix="pin node 22"))
    assert text.endswith(f"{FIX_NOTE} pin node 22\n")
