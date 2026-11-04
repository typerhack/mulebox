"""Fixtures for client tests: temporary git repos and a scripted fake coordinator.

Nothing here contacts a real host or touches the user's git config: git runs with `-c`
flags for the identity, and ssh is replaced by fake_coordinator.py.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mulebox.common import ssh
from mulebox.common.config import ClientConfig, load_node_config
from mulebox.coordinator.node import open_local

FAKE = Path(__file__).with_name("fake_coordinator.py")
LOCAL_SSH = Path(__file__).with_name("local_ssh.py")
GIT_ID = ["-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false"]


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *GIT_ID, *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return proc.stdout


def write(repo: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


PROJECT_YML = "project: example-app\njobs:\n  check: echo ok\n  test: exit 3\n"


@pytest.fixture
def make_repo(tmp_path):
    """make_repo(tracked={...}, untracked={...}) -> repo path with one commit."""

    def make(tracked=None, untracked=None, name="repo", commit=True):
        repo = tmp_path / name
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        write(repo, {".mulebox.yml": PROJECT_YML, **(tracked or {})})
        git(repo, "add", "-A", "-f")
        if commit:
            git(repo, "commit", "-q", "-m", "init")
        write(repo, untracked or {})
        return repo

    return make


class FakeCoordinator:
    def __init__(self, folder: Path) -> None:
        self.dir = folder

    def scenario(self, **values) -> None:
        (self.dir / "scenario.json").write_text(json.dumps(values))

    def requests(self) -> list[dict]:
        path = self.dir / "requests.jsonl"
        if not path.exists():
            return []
        return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]

    def argv(self) -> list[str]:
        return json.loads((self.dir / "argv.json").read_text())

    def upload(self) -> bytes:
        return (self.dir / "upload.tar.gz").read_bytes()


@pytest.fixture
def fake(tmp_path, monkeypatch):
    folder = tmp_path / "fake"
    folder.mkdir()
    wrapper = folder / "fake-ssh"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    wrapper.chmod(0o755)
    monkeypatch.setattr(ssh, "SSH_BINARY", str(wrapper))
    monkeypatch.setenv("FAKE_DIR", str(folder))
    config = tmp_path / "client.toml"
    config.write_text('coordinator = "build-1"\n')
    monkeypatch.setenv("MULEBOX_CONFIG", str(config))
    return FakeCoordinator(folder)


class LocalMachine:
    """A temporary node, its store open for tests to look at, reached through local_ssh.py."""

    def __init__(self, root: Path, store, staging) -> None:
        self.root, self.store, self.staging = root, store, staging
        self.down_flag = root / "down"

    def drop_connection(self, times: int) -> None:
        """The next `times` ssh connections fail."""
        self.down_flag.write_text(str(times))


@pytest.fixture
def local(tmp_path, monkeypatch):
    """The real coordinator code behind a stand-in for ssh; no host is contacted."""
    root = tmp_path / "machine"
    names = {name: root / name for name in ("jobs", "cache", "staging", "runners")}
    for folder in names.values():
        folder.mkdir(parents=True)
    lines = ['name = "build-1"', 'roles = ["coordinator", "worker"]', "slots = 4", "[roots]"]
    lines += [f'{name} = "{folder}"' for name, folder in names.items()]
    node_file = root / "node.toml"
    node_file.write_text("\n".join(lines) + "\n")
    wrapper = root / "local-ssh"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{LOCAL_SSH}" "$@"\n')
    wrapper.chmod(0o755)
    monkeypatch.setattr(ssh, "SSH_BINARY", str(wrapper))
    monkeypatch.setenv("LOCAL_NODE", str(node_file))
    monkeypatch.setenv("LOCAL_SSH_DOWN", str(root / "down"))
    config = tmp_path / "client.toml"
    config.write_text('coordinator = "build-1"\n')
    monkeypatch.setenv("MULEBOX_CONFIG", str(config))
    store, staging = open_local(load_node_config(node_file))
    yield LocalMachine(root, store, staging)
    store.close()


@pytest.fixture
def in_project(make_repo, monkeypatch):
    repo = make_repo()
    monkeypatch.chdir(repo)
    return repo


@pytest.fixture
def client_config():
    return ClientConfig(coordinator="build-1")
