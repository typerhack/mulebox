"""Pinned toolchains under `<cache>/toolchains/<name>/<version>`, prepended to a job's PATH.

- node: the official `node-v<ver>-<system>-<cpu>.tar.xz` from nodejs.org (`linux-x64`,
  `darwin-arm64`, ...: `node_build`), verified against
  that release's `SHASUMS256.txt`, extracted safely (archive.py).
- pnpm: `npm install -g --prefix <cache>/toolchains/pnpm/<ver> pnpm@<ver>`, run with an
  installed node toolchain (the newest one).

Installs go to a temporary folder next to the final one and are renamed into place, so a
half-finished install is never picked up. Temporary folders are removed through safepath. A lost
network is tried again from the start, as the install has nothing to do with the project, and if
it stays lost the error says so instead of offering another version.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from mulebox.common import download
from mulebox.common.errors import MuleboxError
from mulebox.common.ids import new_ulid
from mulebox.common.network_errors import REGISTRY
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.worker.archive import extract_tar
from mulebox.worker.paths import NodePaths

NODE_DIST = "https://nodejs.org/dist"
KNOWN = ("node", "pnpm")
NPM_TIMEOUT_S = 900
TRIES = 3
WAIT_S = 5  # times the try: 5 s, then 10 s
_VERSION_RE = re.compile(r"\d{1,4}\.\d{1,4}\.\d{1,4}")

Fetch = Callable[[str, Path], None]  # download url into a new file
Run = Callable[[list[str], Mapping[str, str]], subprocess.CompletedProcess]


class ToolchainError(MuleboxError):
    """A toolchain is missing, unknown, or could not be installed."""


class ToolchainNetwork(ToolchainError):
    """The install lost its network; the same install can work later."""


def http_fetch(url: str, dest: Path) -> None:
    try:
        download.fetch_file(url, dest)
    except download.NetworkLost as exc:
        raise ToolchainNetwork(str(exc)) from exc
    except download.DownloadError as exc:
        raise ToolchainError(str(exc)) from exc


def run_command(argv: list[str], env: Mapping[str, str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, env=dict(env), capture_output=True, text=True,
                              timeout=NPM_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolchainError(f"`{argv[0]}` failed: {exc}") from exc


def _check(name: str, version: str) -> None:
    if name not in KNOWN:
        raise ToolchainError(f"unknown toolchain {name!r}; known: {', '.join(KNOWN)}")
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise ToolchainError(f"{name} version must look like 22.22.3, got {version!r}")


def toolchain_dir(paths: NodePaths, name: str, version: str) -> Path:
    _check(name, version)
    return paths.toolchains_dir() / name / version


def path_for(paths: NodePaths, toolchain: Mapping[str, str]) -> list[Path]:
    """`bin` folders for a project's toolchain map, in its order; error if one is missing."""
    bins = []
    for name, version in toolchain.items():
        bin_dir = toolchain_dir(paths, name, version) / "bin"
        if not bin_dir.is_dir():
            raise ToolchainError(_not_installed(paths, name, version))
        bins.append(bin_dir)
    return bins


def missing(paths: NodePaths, toolchain: Mapping[str, str]) -> list[tuple[str, str]]:
    """What a job's toolchain map still needs, node first: pnpm installs through it."""
    gaps = [(name, version) for name, version in toolchain.items()
            if not (toolchain_dir(paths, name, version) / "bin").is_dir()]
    return sorted(gaps, key=lambda gap: gap[0] != "node")


def _not_installed(paths: NodePaths, name: str, version: str) -> str:
    """What is missing, what is there instead, and how to get what was asked for."""
    have = [v for n, v in installed(paths) if n == name]
    choice = (f"installed {name} versions: {', '.join(have)}; use one of them in .mulebox.yml"
              if have else f"no {name} version is installed")
    return (f"toolchain {name} {version} is not installed on this worker ({choice}), or "
            f"run `mulebox toolchain install {name} {version}` on it")


def installed(paths: NodePaths) -> list[tuple[str, str]]:
    found = []
    for name in KNOWN:
        base = paths.toolchains_dir() / name
        if base.is_dir():
            for entry in base.iterdir():
                if _VERSION_RE.fullmatch(entry.name) and (entry / "bin").is_dir():
                    found.append((name, entry.name))
    return sorted(found, key=lambda item: (item[0], _version_key(item[1])))


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def node_build(machine: str | None = None, system: str | None = None) -> str:
    """The build of Node.js for this machine, as nodejs.org names it: `linux-x64`, `darwin-arm64`."""
    try:
        return f"{download.system_name(system)}-{download.cpu_arch(machine)}"
    except download.DownloadError as exc:
        raise ToolchainError(f"node: {exc}") from exc


def _expected_sha(sums: str, filename: str) -> str:
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == filename and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            return parts[0]
    raise ToolchainError(f"{filename} is not listed in SHASUMS256.txt")


def _install_node(paths: NodePaths, version: str, tmp: Path, fetch: Fetch, build: str) -> Path:
    stem = f"node-v{version}-{build}"
    base = f"{NODE_DIST}/v{version}"
    downloads = ensure_dir(tmp / "download", paths.roots)
    sums_file, tarball = downloads / "SHASUMS256.txt", downloads / f"{stem}.tar.xz"
    fetch(f"{base}/SHASUMS256.txt", sums_file)
    expected = _expected_sha(sums_file.read_text(encoding="utf-8", errors="replace"),
                             tarball.name)
    fetch(f"{base}/{tarball.name}", tarball)
    actual = download.sha256_file(tarball)
    if actual != expected:
        raise ToolchainError(f"{tarball.name}: sha256 {actual} does not match SHASUMS256.txt")
    return extract_tar(tarball, tmp / "tree", paths.roots, strip_prefix=stem)


def _install_pnpm(paths: NodePaths, version: str, tmp: Path, run: Run,
                  machine_env: Mapping[str, str]) -> Path:
    nodes = [v for n, v in installed(paths) if n == "node"]
    if not nodes:
        raise ToolchainError("pnpm needs a node toolchain; run "
                             "`mulebox toolchain install node <version>` first")
    node_bin = toolchain_dir(paths, "node", nodes[-1]) / "bin"
    tree = ensure_dir(tmp / "tree", paths.roots)
    env = {**os.environ, **machine_env,
           "PATH": os.pathsep.join([str(node_bin), os.environ.get("PATH", "")])}
    argv = [str(node_bin / "npm"), "install", "-g", "--prefix", str(tree), f"pnpm@{version}"]
    proc = run(argv, env)
    if proc.returncode != 0:
        reason = (proc.stderr or "")[-500:]
        kind = ToolchainNetwork if REGISTRY.search(reason) else ToolchainError
        raise kind(f"npm install pnpm@{version} failed: {reason}")
    if not (tree / "bin").is_dir():
        raise ToolchainError(f"npm install pnpm@{version} did not create {tree / 'bin'}")
    return tree


def install_missing(paths: NodePaths, gaps: list[tuple[str, str]],
                    install_one: Callable[[NodePaths, str, str], Path]) -> None:
    """A job's first use of a version: install it, or say why not and what is here instead."""
    for name, version in gaps:
        try:
            install_one(paths, name, version)
        except ToolchainNetwork as exc:
            raise ToolchainNetwork(f"could not install {name} {version}: the machine lost its "
                                   f"network, {TRIES} tries ({exc}). Nothing is wrong with the "
                                   "project or the version; run the job again once the network "
                                   "is back") from exc
        except (MuleboxError, OSError) as exc:
            raise ToolchainError(f"could not install {name} {version}: {exc}. "
                                 f"{_not_installed(paths, name, version)}") from exc


def install(paths: NodePaths, name: str, version: str, *, fetch: Fetch = http_fetch,
            run: Run = run_command, build: str | None = None,
            machine_env: Mapping[str, str] | None = None,
            sleep: Callable[[float], None] = time.sleep) -> Path:
    """Install a toolchain; return its folder. Already installed: return it unchanged.
    `machine_env`: node.toml's `[job_env]`, as what a machine's network needs, such as
    `NODE_OPTIONS`, a job's installs need as well."""
    for attempt in range(1, TRIES + 1):
        try:
            return _install_once(paths, name, version, fetch, run, build, machine_env)
        except ToolchainNetwork:
            if attempt == TRIES:
                raise
            sleep(attempt * WAIT_S)
    raise AssertionError("unreachable")


def _install_once(paths: NodePaths, name: str, version: str, fetch: Fetch, run: Run,
                  build: str | None, machine_env: Mapping[str, str] | None) -> Path:
    final = toolchain_dir(paths, name, version)
    if (final / "bin").is_dir():
        return final
    parent = ensure_dir(final.parent, paths.roots)
    tmp = ensure_dir(parent / f".tmp-{version}-{new_ulid()}", paths.roots)
    try:
        if name == "node":
            tree = _install_node(paths, version, tmp, fetch, build or node_build())
        else:
            tree = _install_pnpm(paths, version, tmp, run, machine_env or {})
        if final.exists():  # a leftover without bin/ from an older, broken install
            remove_tree(final, paths.roots)
        try:
            os.rename(tree, final)
        except OSError:
            if not (final / "bin").is_dir():  # else another job's install got here first
                raise
    finally:
        remove_tree(tmp, paths.roots)
    return final
