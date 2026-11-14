"""`mulebox machine config`: the request it sends and what it prints (client/machine_config.py)."""

import time

import pytest

from mulebox.cli import build_parser
from mulebox.client import machine_config
from mulebox.client.remote import CoordinatorError
from mulebox.common.protocol import MessageType
from mulebox.coordinator import api
from tests.coordinator.conftest import root_map, staging, store  # noqa: F401
from tests.coordinator.helpers import request

GB = 1 << 30


class StoreRemote:
    """The real coordinator code behind `Remote.call`."""

    def __init__(self, store, staging):
        self.store, self.staging, self.sent = store, staging, []

    def call(self, msg):
        self.sent.append(msg.body)
        reply = api.handle(self.store, self.staging, msg, time.time())
        if reply.type is MessageType.ERROR:
            raise CoordinatorError(reply.body["message"], reply.body["code"])
        return reply


@pytest.fixture
def remote(store, staging, monkeypatch):  # noqa: F811
    body = {"worker": "build-1", "capabilities": [], "free_slots": 2,
            "settings": {"slots": 2, "priority": "normal", "dev": False},
            "load": {"cores": 16, "memory": {"total": 32 * GB, "available": 0, "used": 32 * GB}}}
    api.handle(store, staging, request("claim", **body), time.time())
    fake = StoreRemote(store, staging)
    monkeypatch.setattr(machine_config, "connect", lambda: fake)
    return fake


def run(*argv):
    args = build_parser().parse_args(["machine", "config", *argv])
    return args.func(args)


def test_it_shows_the_values_and_the_suggestion(remote, capsys):
    assert run("build-1") == 0
    out = capsys.readouterr().out
    assert "slots:     2" in out and "priority:  normal" in out
    assert "suggested: 4 slot(s), from 16 cores and 34.4 GB" in out
    assert remote.sent == [{"worker": "build-1"}]


def test_a_change_is_sent_and_shown_as_waiting(remote, capsys):
    assert run("build-1", "--slots", "3", "--priority", "preferred") == 0
    assert remote.sent[-1] == {"worker": "build-1", "slots": 3, "priority": "preferred"}
    assert "waiting:   priority preferred, slots 3; the machine applies it within seconds" in \
        capsys.readouterr().out
    assert run("build-1", "--cancel", "--json") == 0
    assert '"pending": null' in capsys.readouterr().out


def test_wait_gives_up_with_exit_1_when_the_machine_does_not_apply_it(remote, monkeypatch):
    monkeypatch.setattr(machine_config, "WAIT_S", 0.0)
    assert run("build-1", "--slots", "3", "--wait") == 1


def test_bad_values_are_refused_by_the_parser_or_the_coordinator(remote, capsys):
    with pytest.raises(SystemExit):
        run("build-1", "--priority", "first")
    assert run("build-1", "--slots", "0") != 0
    assert "from 1 to 64" in capsys.readouterr().err


def test_dev_mode_is_shown_asked_and_named_in_the_list(remote, capsys, monkeypatch):
    assert run("build-1") == 0
    assert "dev mode:  off" in capsys.readouterr().out
    assert run("build-1", "--dev", "on") == 0
    assert remote.sent[-1] == {"worker": "build-1", "dev": True}
    assert "waiting:   dev on; the machine applies it" in capsys.readouterr().out
    from mulebox.client import machine_commands
    monkeypatch.setattr(machine_commands, "connect", lambda: remote)
    args = build_parser().parse_args(["machine", "list"])
    assert args.func(args) == 0
    assert "build-1              dev " in capsys.readouterr().out  # asked counts at once
