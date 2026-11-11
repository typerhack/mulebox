"""Add, list and remove GitHub Actions runners on this build machine (docs/interfaces-m3.md).

The token (registration or removal) is handed in by the caller, read from stdin by the
CLI. It never goes into argv: `config.sh` gets it through `ACTIONS_RUNNER_INPUT_TOKEN`,
which the runner reads in place of `--token` and then clears from its own environment.
Any `config.sh` output shown in an error is redacted with the token as a known secret,
and no log line or error message is built from the token.

`add`: refuse an existing folder, download and verify the runner (release.py), extract it
into a hidden temporary folder and rename it to `<runners>/<name>`, run `config.sh`, write
the hook scripts and `.env` lines, then enable and start `mulebox-runner@<name>.service`.
A failure before the unit starts removes the folder again (through safepath).
`remove`: stop and disable the unit, `config.sh remove`, remove the folder (safepath).
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mulebox.common.errors import MuleboxError
from mulebox.common.ids import new_ulid
from mulebox.common.redact import Redactor
from mulebox.common.safepath import remove_tree
from mulebox.runners import layout, release
from mulebox.runners.names import (
    RunnerUsageError,
    check_name,
    check_repo,
    repo_url,
    unit_name,
)
from mulebox.worker.paths import NodePaths
from mulebox.worker.systemd import default_runner

TOKEN_ENV = "ACTIONS_RUNNER_INPUT_TOKEN"
CONFIG_TIMEOUT_S = 300
OUTPUT_CHARS = 2000
TEMPLATE = "mulebox-runner@.service"

ConfigRun = Callable[[Sequence[str], Path, Mapping[str, str]], subprocess.CompletedProcess]
Systemctl = Callable[[Sequence[str]], subprocess.CompletedProcess]
Say = Callable[[str], None]


class RunnerError(MuleboxError):
    """A runner could not be added, listed or removed."""


def run_config(argv: Sequence[str], cwd: Path, env: Mapping[str, str]
               ) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(list(argv), cwd=cwd, env=dict(env), capture_output=True,
                              text=True, timeout=CONFIG_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise RunnerError(f"`{argv[0]} {argv[1]}` did not finish within "
                          f"{CONFIG_TIMEOUT_S} s") from None
    except OSError as exc:
        raise RunnerError(f"cannot run {argv[0]}: {exc.strerror}") from None


@dataclass
class Machine:
    """What runner management touches on this machine; tests replace the callables."""

    paths: NodePaths
    node: str
    config_run: ConfigRun = run_config
    systemctl: Systemctl = default_runner
    home: Path = field(default_factory=Path.home)
    unit_dir: Path | None = None  # default: <home>/.config/systemd/user
    arch: str | None = None
    fetch_json: release.FetchJson | None = None
    fetch_file: release.FetchFile | None = None
    say: Say = print


def config_argv(folder: Path, repo: str, name: str, labels: Sequence[str]) -> list[str]:
    """`config.sh` for registration; the token is passed in the environment, not here."""
    return [str(folder / "config.sh"), "--unattended", "--url", repo_url(repo),
            "--name", check_name(name), "--labels", ",".join(labels),
            "--work", "_work", "--replace"]


def remove_argv(folder: Path) -> list[str]:
    return [str(folder / "config.sh"), "remove"]


def _config(m: Machine, argv: list[str], folder: Path, token: str, what: str) -> None:
    redactor = Redactor([token])
    proc = m.config_run(argv, folder, {**os.environ, TOKEN_ENV: token})
    if proc.returncode != 0:
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()[-OUTPUT_CHARS:]
        raise RunnerError(f"{what} failed (exit {proc.returncode}): "
                          f"{redactor.redact(output) or 'no output'}")


def _systemctl(m: Machine, *args: str) -> subprocess.CompletedProcess:
    return m.systemctl(["systemctl", "--user", *args])


def _check_token(token: str) -> str:
    if not isinstance(token, str) or not token or len(token) > 1024 or any(
            c.isspace() or not c.isprintable() for c in token):
        raise RunnerUsageError("the token on stdin is empty or not a single word")
    return token


def _download(m: Machine, folder: Path) -> str:
    kwargs = {"fetch_json": m.fetch_json} if m.fetch_json else {}
    found = release.latest_release(m.arch, **kwargs)
    m.say(f"Runner {found.version} ({found.asset})")
    file_kwargs = {"fetch": m.fetch_file} if m.fetch_file else {}
    tarball = release.fetch_verified(m.paths, found, **file_kwargs)
    m.say(f"Verified sha256 {found.sha256}")
    tmp = m.paths.runners / f".tmp-{folder.name}-{new_ulid()}"
    try:
        release.extract(m.paths, tarball, tmp)
        os.rename(tmp, folder)  # fails if the folder appeared meanwhile
    except OSError as exc:
        raise RunnerError(f"cannot move the runner into {folder}: {exc.strerror}") from exc
    finally:
        remove_tree(tmp, m.paths.roots)
    return found.version


def add(m: Machine, repo: str, token: str, *, name: str, labels: Sequence[str]) -> Path:
    """Register a runner for repo and start its service; return its folder."""
    check_repo(repo)
    _check_token(token)
    folder = layout.runner_dir(m.paths, name)
    layout.check_unit_root(m.paths, m.home)
    template = (m.unit_dir or m.home / ".config" / "systemd" / "user") / TEMPLATE
    if not template.is_file():
        raise RunnerError(f"{template} is missing; rerun the mulebox installer")
    if folder.exists() or folder.is_symlink():
        raise RunnerUsageError(f"runner {name} already exists in {folder}; "
                               f"remove it first with `mulebox runner remove {name}`")
    version = _download(m, folder)
    try:
        m.say(f"Registering {name} for {repo} (labels {','.join(labels)})")
        _config(m, config_argv(folder, repo, name, labels), folder, token, "config.sh")
        layout.set_env_hooks(m.paths, folder, layout.write_hooks(m.paths, folder))
        layout.write_meta(m.paths, folder, {
            "name": name, "repo": repo, "labels": list(labels), "version": version,
            "added_at": int(time.time())})
    except BaseException:
        remove_tree(folder, m.paths.roots)
        raise
    unit = unit_name(name)
    for args in (("daemon-reload",), ("enable", "--now", unit)):
        proc = _systemctl(m, *args)
        if proc.returncode != 0:
            raise RunnerError(f"`systemctl --user {' '.join(args)}` failed: "
                              f"{(proc.stderr or '').strip()[-500:]}. The runner is "
                              f"registered; start it with `systemctl --user enable --now {unit}`")
    m.say(f"Started {unit}")
    return folder


@dataclass(frozen=True)
class RunnerInfo:
    name: str
    repo: str
    state: str
    busy: bool


def list_runners(m: Machine) -> list[RunnerInfo]:
    found = []
    for folder in layout.runner_folders(m.paths):
        meta = layout.read_meta(folder)
        try:
            unit = unit_name(folder.name)
        except RunnerUsageError:
            continue  # not a folder runner add could have made
        proc = _systemctl(m, "is-active", unit)
        state = (proc.stdout or "").strip() or "unknown"
        found.append(RunnerInfo(folder.name, str(meta.get("repo", "-")), state,
                                layout.is_busy(folder)))
    return found


def find_by_repo(m: Machine, repo: str) -> str:
    """The one runner registered for repo."""
    check_repo(repo)
    names = [f.name for f in layout.runner_folders(m.paths)
             if layout.read_meta(f).get("repo") == repo]
    if not names:
        raise RunnerUsageError(f"no runner for {repo} on this machine")
    if len(names) > 1:
        raise RunnerUsageError(f"several runners for {repo} ({', '.join(names)}); name one")
    return names[0]


def check_runner_repo(m: Machine, name: str, repo: str) -> None:
    """Refuse when runner name is registered for another repository."""
    found = layout.read_meta(layout.runner_dir(m.paths, name)).get("repo")
    if found is not None and found != check_repo(repo):
        raise RunnerUsageError(f"runner {name} belongs to {found}, not {repo}")


def remove(m: Machine, name: str, token: str) -> None:
    """Stop the service, unregister from GitHub, and remove the runner folder."""
    _check_token(token)
    folder = layout.runner_dir(m.paths, name)
    if not folder.is_dir() or folder.is_symlink():
        raise RunnerUsageError(f"no runner {name} in {m.paths.runners}")
    unit = unit_name(name)
    proc = _systemctl(m, "disable", "--now", unit)
    if proc.returncode != 0:
        raise RunnerError(f"`systemctl --user disable --now {unit}` failed: "
                          f"{(proc.stderr or '').strip()[-500:]}")
    m.say(f"Stopped {unit}")
    if (folder / ".runner").exists():
        _config(m, remove_argv(folder), folder, token, "config.sh remove")
        m.say(f"Unregistered {name} from GitHub")
    remove_tree(folder, m.paths.roots)
    m.say(f"Removed {folder}")
    # A runner stopped mid-listen can leave its unit `failed`, which systemd would go on listing.
    _systemctl(m, "reset-failed", unit)
