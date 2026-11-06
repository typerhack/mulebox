"""`mulebox setup <host>`: from a machine you can log in to, to a job that passed on it.

Each step says what it does and stops with what to do about it. It can run again at any time: an
upgrade keeps `node.toml`, and the laptop's config is written only if there is none.
"""

import json
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

from mulebox.client import sshio, wheel
from mulebox.client.remote import Remote, request
from mulebox.common import ssh
from mulebox.common.config import ClientConfig, client_config_path, load_client_config
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import MessageType

CONNECT_S = 10
LOGIN_TIMEOUT_S = 30
INSTALL_TIMEOUT_S = 1200
PROGRAM = ".mulebox/bin/mulebox"
CHECK_PROJECT = "mulebox-setup-check"
_UNPACK = 'mkdir -p "$HOME/.mulebox/tmp" && tar xzf - -C "$HOME/.mulebox/tmp"'
_RESTART = "systemctl --user restart mulebox-worker"
Say = Callable[[str], None]


class SetupError(MuleboxError):
    """A step failed; the message says what to do."""


def check_login(target: str) -> None:
    try:
        ssh.run_remote(target, ["true"], timeout_s=LOGIN_TIMEOUT_S, connect_timeout_s=CONNECT_S)
    except ssh.SSHError as exc:
        raise SetupError(
            f"cannot log in to {target} without a prompt, and mulebox never answers one.\n"
            f"Make `ssh {target} true` work: log in once by hand so its host key is known, "
            f"copy your key with `ssh-copy-id {target}`, and load a key with a passphrase into "
            f"your ssh agent.\n({exc})") from exc


def running_jobs(target: str) -> list[str]:
    """Jobs on the machine now; none if mulebox is not there yet, or is too old to say."""
    remote = Remote(ClientConfig(coordinator=target, remote_bin=f"~/{PROGRAM}",
                                 connect_timeout_s=CONNECT_S))
    try:
        rows = remote.call(request(MessageType.QUEUE)).body.get("jobs") or []
    except (MuleboxError, OSError):
        return []
    return [row["job_id"] for row in rows
            if row.get("state") in ("starting", "running", "cleaning")]


def _pack(folder: Path) -> tuple[Path, str]:
    """A tar.gz of the wheel and the installer's files in `folder`; the wheel's name."""
    built = wheel.build(folder)
    machine = resources.files("mulebox.machine")
    bundle = folder / "bundle.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        tar.add(built, built.name)
        for name in ("install.sh", "node.toml.example", "systemd"):
            tar.add(str(machine / name), name)
    return bundle, built.name


def install(target: str) -> None:
    with tempfile.TemporaryDirectory(prefix="mulebox-setup-") as folder:
        bundle, name = _pack(Path(folder))
        sent = sshio.run_with_file(target, ["sh", "-c", _UNPACK], bundle,
                                   connect_timeout_s=CONNECT_S)
    sshio.check_exit(target, ["tar"], sent.exit_code, sent.stderr)
    script = (f'exec bash "$HOME/.mulebox/tmp/install.sh" '
              f'"$HOME/.mulebox/tmp/"{shlex.quote(name)}')
    done = subprocess.run(ssh.ssh_command(target, ["sh", "-c", script], CONNECT_S),
                          timeout=INSTALL_TIMEOUT_S, stdin=subprocess.DEVNULL, check=False)
    if done.returncode != 0:
        raise SetupError(f"the installer on {target} stopped; what it printed above says why")


def find_offers(target: str, say: Say) -> None:
    result = ssh.run_remote(target, [PROGRAM, "node-offers", "--write"], timeout_s=LOGIN_TIMEOUT_S,
                            connect_timeout_s=CONNECT_S)
    offers: dict[str, Any] = json.loads(result.stdout)
    if offers["added"]:
        ssh.run_remote(target, ["sh", "-c", _RESTART], timeout_s=LOGIN_TIMEOUT_S,
                       connect_timeout_s=CONNECT_S)
    say(f"it offers: {', '.join(offers['capabilities']) or 'plain jobs'}")
    if offers["docker"] == "no-access":
        say(f"Docker is there, but this user cannot use it. On {target}, run "
            "`sudo usermod -aG docker $USER`, log in again, then `mulebox setup` again")
    elif offers["docker"] == "missing":
        say("no Docker, so projects with `compose:` cannot run here until it is installed")


def write_client_config(target: str, say: Say) -> None:
    path = client_config_path()
    if path.exists():
        current = load_client_config(path).coordinator
        if current != target:
            say(f"{path} points at {current}; left as it is. Edit `coordinator` to use {target}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'coordinator = "{target}"\n', encoding="utf-8")
    say(f"wrote {path}")


def _git(folder: str, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=mulebox", "-c", "user.email=mulebox@example.com",
                    *args], cwd=folder, capture_output=True, check=True)


def prove(target: str, say: Say) -> None:
    """A real job through the real queue, in a scratch project; nothing of it stays."""
    with tempfile.TemporaryDirectory(prefix="mulebox-setup-") as folder:
        Path(folder, ".mulebox.yml").write_text(
            f"project: {CHECK_PROJECT}\njobs:\n  check: uname -sr\n", encoding="utf-8")
        Path(folder, "client.toml").write_text(f'coordinator = "{target}"\n', encoding="utf-8")
        Path(folder, ".gitignore").write_text("client.toml\n", encoding="utf-8")
        _git(folder, "init", "-q")
        _git(folder, "add", "-A")
        _git(folder, "commit", "-q", "-m", "check")
        env = {**os.environ, "MULEBOX_CONFIG": str(Path(folder, "client.toml"))}
        done = subprocess.run([sys.executable, "-m", "mulebox.cli", "check", "--again"], cwd=folder,
                              env=env, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SetupError(f"the first job did not pass (exit {done.returncode}):\n{done.stderr}")
    say("a first job passed")
    ssh.run_remote(target, [PROGRAM, "project-home", "reset", CHECK_PROJECT, "--yes"],
                   timeout_s=LOGIN_TIMEOUT_S, connect_timeout_s=CONNECT_S)


def run(target: str, say: Say, now: bool = False) -> None:
    say(f"checking the login to {target}")
    check_login(target)
    if not now and (jobs := running_jobs(target)):
        raise SetupError(f"{len(jobs)} job(s) are running on {target}, and an upgrade would stop "
                         "them. Run this again after them, or add --now.")
    try:
        say(f"installing mulebox on {target}")
        install(target)
        find_offers(target, say)
        write_client_config(target, say)
        say("running a first job")
        prove(target, say)
    except (MuleboxError, OSError, ValueError, subprocess.SubprocessError) as exc:
        if isinstance(exc, SetupError):
            raise
        raise SetupError(f"setup stopped: {exc}. Fix that and run it again; it starts over "
                         "safely") from exc
    say(f"{target} is ready. In a project: `mulebox init`, then `mulebox check`")
