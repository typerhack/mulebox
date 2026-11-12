"""`mulebox setup <host>`: from a machine you can log in to, to a job that passed on it.

Each step says what it does and stops with what to do about it. It can run again at any time: an
upgrade keeps `node.toml`, and the dev machine's config is written only if there is none.
"""

import json
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
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
HOLD_WHILE_WAITING_S = 120
HOLD_WHILE_INSTALLING_S = 1500  # past INSTALL_TIMEOUT_S; ended as soon as the install is
POLL_IDLE_S = 10.0
_UNPACK = 'mkdir -p "$HOME/.mulebox/tmp" && tar xzf - -C "$HOME/.mulebox/tmp"'
_RESTART = f'"$HOME/{PROGRAM}" service restart worker'
Say = Callable[[str], None]


class SetupError(MuleboxError):
    """A step failed; the message says what to do."""


# ssh's own words for a machine that cannot be reached at all: no key would help, so the
# advice is about the name or the network, not about logging in.
_UNKNOWN_NAME = ("could not resolve hostname", "name or service not known")
_UNREACHABLE = ("connection refused", "timed out", "no route to host", "network is unreachable")


def _login_advice(target: str, detail: str) -> str:
    text = detail.lower()
    if any(word in text for word in _UNKNOWN_NAME):
        return (f"this dev machine does not know a machine called {target}.\n"
                "Give its address, such as `mulebox setup 192.168.1.50`, or a name from "
                f"~/.ssh/config (`Host {target}` with `HostName <address>` under it). Then check "
                f"that `ssh {target} true` works.")
    if any(word in text for word in _UNREACHABLE):
        return (f"cannot reach {target}.\n"
                "Check that it is on, that this dev machine is on its network (or VPN), and that it "
                f"runs an ssh server; then that `ssh {target} true` works.")
    return (f"cannot log in to {target} without a prompt, and mulebox never answers one.\n"
            f"Make `ssh {target} true` work. With no key on this dev machine yet, make one: "
            "`ssh-keygen -t ed25519`. Copy it with `ssh-copy-id`, which asks for the password "
            f"there once, so a person runs it: `ssh-copy-id {target}` if your user name there is "
            f"the same as here, else `ssh-copy-id <user>@{target}`, or put `User <user>` under "
            f"`Host {target}` in ~/.ssh/config. Then `ssh {target} true` once, to accept its "
            "host key. A key with a passphrase must be loaded into your ssh agent "
            "(docs/getting-started.md, What you need).")


def check_login(target: str) -> None:
    try:
        ssh.run_remote(target, ["true"], timeout_s=LOGIN_TIMEOUT_S, connect_timeout_s=CONNECT_S)
    except ssh.SSHError as exc:
        raise SetupError(f"{_login_advice(target, str(exc))}\n({exc})") from exc


def remote_for(target: str) -> Remote:
    return Remote(ClientConfig(coordinator=target, remote_bin=f"~/{PROGRAM}",
                               connect_timeout_s=CONNECT_S))


def running_jobs(target: str) -> list[str]:
    """Jobs on the machine now; none if mulebox is not there yet, or is too old to say."""
    try:
        rows = remote_for(target).call(request(MessageType.QUEUE)).body.get("jobs") or []
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
        for name in ("install.sh", "node.toml.example"):
            tar.add(str(machine / name), name)
    return bundle, built.name


def install(target: str, env: dict[str, str] | None = None) -> None:
    """Install or upgrade mulebox on `target`; `env` goes to install.sh (MULEBOX_COORDINATOR)."""
    with tempfile.TemporaryDirectory(prefix="mulebox-setup-") as folder:
        bundle, name = _pack(Path(folder))
        sent = sshio.run_with_file(target, ["sh", "-c", _UNPACK], bundle,
                                   connect_timeout_s=CONNECT_S)
    sshio.check_exit(target, ["tar"], sent.exit_code, sent.stderr)
    exports = "".join(f"export {name}={shlex.quote(value)}; "
                      for name, value in (env or {}).items())
    script = (f'{exports}exec bash "$HOME/.mulebox/tmp/install.sh" '
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


def _this_mulebox() -> list[str]:
    """How to run the mulebox that is running."""
    return [sys.executable, "-m", "mulebox"]


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
        done = subprocess.run([*_this_mulebox(), "check", "--again"], cwd=folder, env=env,
                              capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SetupError(f"the first job did not pass (exit {done.returncode}):\n{done.stderr}")
    say("a first job passed")
    ssh.run_remote(target, [PROGRAM, "project-home", "reset", CHECK_PROJECT, "--yes"],
                   timeout_s=LOGIN_TIMEOUT_S, connect_timeout_s=CONNECT_S)


def _drain(target: str, seconds: int) -> list[str] | None:
    """Hold new jobs back; the jobs still running, or None if the machine cannot hold them."""
    try:
        return remote_for(target).call(request(MessageType.DRAIN, seconds=seconds)).body["running"]
    except (MuleboxError, OSError):  # not installed yet, or too old
        return None


def wait_until_idle(target: str, say: Say) -> bool:
    """Hold new jobs back until the running ones end. True if the machine is holding them. The
    hold is renewed while this waits, so a killed dev machine stops nothing for long."""
    told = None
    while True:
        running = _drain(target, HOLD_WHILE_WAITING_S)
        holding = running is not None
        jobs = running if holding else running_jobs(target)
        if not jobs:
            if holding:
                _drain(target, HOLD_WHILE_INSTALLING_S)
            return holding
        if len(jobs) != told:
            told = len(jobs)
            say(f"waiting for {told} running job(s) to end; new jobs wait in line")
        time.sleep(POLL_IDLE_S)


def run(target: str, say: Say, now: bool = False, when_idle: bool = False) -> None:
    say(f"checking the login to {target}")
    check_login(target)
    holding = False
    if when_idle:
        holding = wait_until_idle(target, say)
    elif not now and (jobs := running_jobs(target)):
        raise SetupError(f"{len(jobs)} job(s) are running on {target}, and an upgrade would stop "
                         "them. Add --when-idle to wait for them, or --now.")
    try:
        say(f"installing mulebox on {target}")
        install(target)
        find_offers(target, say)
        write_client_config(target, say)
        if holding:
            _drain(target, 0)
            holding = False
        say("running a first job")
        prove(target, say)
    except (MuleboxError, OSError, ValueError, subprocess.SubprocessError) as exc:
        if isinstance(exc, SetupError):
            raise
        raise SetupError(f"setup stopped: {exc}. Fix that and run it again; it starts over "
                         "safely") from exc
    finally:
        if holding:
            _drain(target, 0)
    say(f"{target} is ready. In a project: `mulebox init`, then `mulebox check`")
