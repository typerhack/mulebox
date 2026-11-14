"""`mulebox setup --worker-of`: the coordinator's address, the key's name, the steps in order."""

import subprocess

import pytest

from mulebox.client import setup, setup_worker
from mulebox.client.setup import SetupError


def _ssh_g(monkeypatch, stdout, code=0):
    monkeypatch.setattr(setup_worker.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], code, stdout=stdout, stderr=""))


def test_address_from_ssh_config(monkeypatch):
    _ssh_g(monkeypatch, "user alice\nhostname 192.168.1.50\nport 2222\nbatchmode no\n")
    assert setup_worker.coordinator_address("pc") == "ssh://alice@192.168.1.50:2222"


def test_address_unknown_says_what_to_give(monkeypatch):
    _ssh_g(monkeypatch, "", code=255)
    with pytest.raises(SetupError, match="--coordinator-address"):
        setup_worker.coordinator_address("pc")


def test_marker_name():
    assert setup_worker.marker_name("alice@192.168.1.51") == "alice-192.168.1.51"


def test_steps_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(setup, "check_login", lambda t: calls.append(("login", t)))
    monkeypatch.setattr(setup_worker, "_run", lambda t, s, stdin=None: "build-2\n")
    monkeypatch.setattr(setup_worker, "worker_jobs", lambda c, n: [])
    monkeypatch.setattr(setup_worker, "make_key", lambda w: (
        calls.append(("key", w)) or ("ssh-ed25519 AAAA k", "/home/alice/.config/mulebox/coordinator_key")))
    monkeypatch.setattr(setup_worker, "authorize", lambda c, n, k: calls.append(("auth", c, n)))
    monkeypatch.setattr(setup, "install", lambda t, env: calls.append(("install", t, env)))
    monkeypatch.setattr(setup, "find_offers", lambda t, say: calls.append(("offers", t)))
    monkeypatch.setattr(setup_worker, "wait_online", lambda c, n: {"slots": 2, "capabilities": []})
    said = []
    setup_worker.run("build-2", "pc", said.append, address="ssh://alice@192.168.1.50:22")
    assert [c[0] for c in calls] == ["login", "login", "key", "auth", "install", "offers"]
    assert calls[4][2] == {"MULEBOX_COORDINATOR": "ssh://alice@192.168.1.50:22",
                           "MULEBOX_COORDINATOR_KEY": "/home/alice/.config/mulebox/coordinator_key"}
    assert "build-2 is in the queue" in said[-1]


def test_dev_starts_the_node_in_dev_mode(monkeypatch):
    calls, asked = [], []
    monkeypatch.setattr(setup, "check_login", lambda t: None)
    monkeypatch.setattr(setup_worker, "_run", lambda t, s, stdin=None: "build-2\n")
    monkeypatch.setattr(setup_worker, "worker_jobs", lambda c, n: [])
    monkeypatch.setattr(setup_worker, "make_key", lambda w: ("ssh-ed25519 AAAA k", "/k"))
    monkeypatch.setattr(setup_worker, "authorize", lambda c, n, k: None)
    monkeypatch.setattr(setup, "install", lambda t, env: calls.append(env))
    monkeypatch.setattr(setup, "find_offers", lambda t, say: None)
    monkeypatch.setattr(setup_worker, "_ask_dev", lambda c, n: asked.append(n))
    monkeypatch.setattr(setup_worker, "wait_online", lambda c, n: {"slots": 2, "dev": True})
    said = []
    setup_worker.run("build-2", "pc", said.append, address="pc", dev=True)
    assert calls[0]["MULEBOX_DEV"] == "1" and asked == ["build-2"]  # before the install only
    assert "dev mode" in said[-1] and "--on build-2" in said[-1]


def test_running_jobs_stop_an_upgrade(monkeypatch):
    monkeypatch.setattr(setup, "check_login", lambda t: None)
    monkeypatch.setattr(setup_worker, "_run", lambda t, s, stdin=None: "build-2\n")
    monkeypatch.setattr(setup_worker, "worker_jobs", lambda c, n: ["job-1"])
    with pytest.raises(SetupError, match="--now"):
        setup_worker.run("build-2", "pc", print, address="ssh://alice@192.168.1.50:22")
