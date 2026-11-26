"""`mulebox hold` and `mulebox release` on the dev machine (client/hold.py)."""

import io
import subprocess

import pytest

from mulebox.client import hold
from mulebox.client.commands import UsageError
from mulebox.common.protocol import Message, MessageType

JOB = "job-01HZZZZZZZZZZZZZZZZZZZZZZZ"
WAITING = {"job_id": JOB, "state": "queued", "go": False, "node": "build-1", "position": 2,
           "waiting_for": "it takes build-1 once it is free", "holds": "the whole node"}
HELD = {**WAITING, "state": "running", "go": True, "until": 1_900_000_000.0}


class Remote:
    def __init__(self, *turns):
        self.turns = list(turns)
        self.asked = []

    def call(self, msg):
        self.asked.append(msg.body["action"])
        if msg.body["action"] == "release":
            body = {"job_id": JOB, "state": "finished", "node": "build-1", "duration_s": 75.0}
        else:
            body = self.turns.pop(0) if len(self.turns) > 1 else self.turns[0]
        return Message(MessageType.STATUS_OK, msg.request_id, body)


def holder(remote, err, run=None, sleeps=None):
    def sleep(s):
        if sleeps is not None:
            sleeps.append(s)
            if len(sleeps) > 5:
                raise KeyboardInterrupt
    return hold.Holder(remote, JOB, err, sleep=sleep,
                       run=run or (lambda argv, check: subprocess.CompletedProcess(argv, 3)))


def test_it_waits_then_runs_the_command_and_lets_go_with_its_exit_code():
    err, remote = io.StringIO(), Remote(WAITING, HELD)
    ran = []
    code = holder(remote, err, run=lambda argv, check: ran.append(argv) or
                  subprocess.CompletedProcess(argv, 3)).run(["./bench.sh"], WAITING)
    assert code == 3 and ran == [["./bench.sh"]]
    assert remote.asked[0] == "turn" and remote.asked[-1] == "release"
    out = err.getvalue()
    assert "waiting for build-1: #2 in line; it takes build-1 once it is free" in out
    assert f"build-1 is yours (the whole node) until" in out and f"mulebox release {JOB}" in out
    assert "let go of build-1 after 1m 15s" in out


def test_without_a_command_it_holds_until_ctrl_c():
    err, sleeps = io.StringIO(), []
    remote = Remote(HELD)
    assert holder(remote, err, sleeps=sleeps).run([], HELD) == 130
    assert sleeps[0] == hold.RENEW_EVERY_S and remote.asked.count("turn") >= 4
    assert remote.asked[-1] == "release"


def test_a_hold_ended_elsewhere_is_said_and_not_released_again():
    err = io.StringIO()
    remote = Remote(HELD, {**HELD, "state": "finished", "go": False, "ended": "its time was up"})
    assert holder(remote, err, sleeps=[]).run([], HELD) == 0
    assert "ended: its time was up" in err.getvalue() and "release" not in remote.asked


def test_ctrl_c_while_waiting_takes_it_out_of_line():
    remote = Remote(WAITING)
    assert holder(remote, io.StringIO(), sleeps=[0] * 5).run(["true"], WAITING) == 130
    assert remote.asked[-1] == "release"


@pytest.mark.parametrize("text, s", [("30m", 1800), ("2h", 7200), ("1.5h", 5400), ("24h", 86400)])
def test_for_reads_minutes_and_hours(text, s):
    assert hold.seconds(text) == s


@pytest.mark.parametrize("text", ["2d", "soon", "25h", "0m"])
def test_a_bad_for_is_refused(text):
    with pytest.raises(UsageError):
        hold.seconds(text)


def test_options_go_anywhere_and_only_what_follows_dashes_is_the_command():
    from mulebox import cli

    parse = cli.build_parser().parse_args
    args = parse(["hold", "build-1", "--slots", "1", "--for", "30m"])
    assert (args.node, args.slots, args.for_, args.argv) == ("build-1", 1, "30m", [])
    args = parse(["hold", "--next", "build-1", "--", "ssh", "build-1", "-v", "--slots", "2"])
    assert args.next and args.slots == 0 and args.argv == ["ssh", "build-1", "-v", "--slots", "2"]
