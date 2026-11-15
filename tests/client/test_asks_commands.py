"""`mulebox storage ask|requests|approve|decline|changes|undo` and `mulebox agents` against the
real coordinator code, and what an agent is told (client/asks_commands.py, client/attention.py)."""

import time

import pytest

from mulebox.cli import build_parser
from mulebox.client import asks_commands, attention
from mulebox.common import storage_policy
from mulebox.coordinator import api
from tests.client.test_machine_config import StoreRemote
from tests.coordinator.conftest import root_map, staging, store  # noqa: F401
from tests.coordinator.helpers import request

GB = 10**9


@pytest.fixture
def remote(store, staging, monkeypatch):  # noqa: F811
    body = {"worker": "build-1", "capabilities": [], "free_slots": 2,
            "settings": {"slots": 2, "priority": "normal", "dev": False, **storage_policy.DEFAULTS},
            "storage": {"at": time.time(), "held": 17 * GB, "policy": {"max_size": "20GB"}}}
    api.handle(store, staging, request("claim", **body), time.time())
    fake = StoreRemote(store, staging)
    monkeypatch.setattr(asks_commands, "connect", lambda: fake)
    monkeypatch.setattr(asks_commands, "_project", lambda: "example-app")
    return fake


def run(*argv):
    args = build_parser().parse_args(list(argv))
    return args.func(args)


def test_ask_then_approve_at_another_size_then_undo(remote, capsys):
    assert run("storage", "ask", "--size", "30GB", "--reason", "three images") == 0
    assert "waits for the owner's answer" in capsys.readouterr().out
    assert run("storage", "requests") == 0
    out = capsys.readouterr().out
    assert "build-1: 30GB asked" in out and "example-app" in out and "ask me first" in out
    assert run("storage", "approve", "--size", "25GB") == 0
    out = capsys.readouterr().out
    assert "20GB to 25GB, approved at another value; asked 30GB; by `mulebox storage" in out
    change = out.split("mulebox storage undo ")[1].split(")")[0]
    assert run("storage", "undo", change) == 0
    assert "25GB to 20GB, undone" in capsys.readouterr().out
    assert run("storage", "changes") == 0
    assert capsys.readouterr().out.count("\n") == 2


def test_decline_with_a_note_and_allow(remote, capsys):
    run("storage", "ask", "--size", "30GB", "--reason", "why")
    assert run("storage", "decline", "--note", "clean first") == 0
    assert "stays 20GB, declined; asked 30GB" in capsys.readouterr().out
    assert run("agents", "allow") == 0
    assert "allow, and record it" in capsys.readouterr().out
    assert run("storage", "ask", "--size", "30GB", "--reason", "why") == 0
    assert "may now use 30GB" in capsys.readouterr().out


def test_what_the_agent_is_told():
    base = {"worker": "build-1", "held": 17 * GB, "warn": 16 * GB, "max": 20 * GB}
    assert "mulebox storage ask --node build-1" in attention.heavy_line(base)
    assert "waits for the owner's answer" in attention.heavy_line(
        {**base, "asked": {"value": "30GB", "at": 1.0}})
    assert "declined 30GB with the note: clean" in attention.heavy_line(
        {**base, "declined": {"value": "30GB", "note": "clean", "at": 1.0}})
    approved = {"node": "build-1", "value": "30GB", "state": "approved",
                "answer": {"value": "25GB"}}
    assert attention.answer_line(approved).endswith("may use 25GB, not the 30GB asked")
    assert "declined" in attention.answer_line({**approved, "state": "declined"})
