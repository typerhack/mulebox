"""Toolchains: verified node install, pnpm through node's npm, clear errors. No network."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from mulebox.worker import toolchains
from mulebox.worker.toolchains import ToolchainError

from .fakes import make_tar

VERSION = "22.22.3"
STEM = f"node-v{VERSION}-linux-x64"


@pytest.fixture
def node_dist(tmp_path):
    """A fake nodejs.org: tarball plus SHASUMS256.txt; fetch copies from it."""
    dist = tmp_path / "dist"
    dist.mkdir()
    tarball = make_tar(dist / f"{STEM}.tar.xz",
                       {f"{STEM}/bin/node": "#!/bin/sh\n", f"{STEM}/LICENSE": "MIT\n"}, mode="w:xz")
    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    (dist / "SHASUMS256.txt").write_text(f"{'0' * 64}  other.tar.gz\n{digest}  {tarball.name}\n")
    urls = []

    def fetch(url, dest):
        urls.append(url)
        dest.write_bytes((dist / url.rsplit("/", 1)[1]).read_bytes())

    fetch.urls = urls
    fetch.dist = dist
    return fetch


def test_install_node(paths, node_dist):
    final = toolchains.install(paths, "node", VERSION, fetch=node_dist, arch="x64")
    assert final == paths.cache / "toolchains" / "node" / VERSION
    assert (final / "bin" / "node").exists()
    assert node_dist.urls == [f"https://nodejs.org/dist/v{VERSION}/SHASUMS256.txt",
                              f"https://nodejs.org/dist/v{VERSION}/{STEM}.tar.xz"]
    assert [p.name for p in final.parent.iterdir()] == [VERSION]  # temp folder removed
    assert toolchains.path_for(paths, {"node": VERSION}) == [final / "bin"]
    assert toolchains.installed(paths) == [("node", VERSION)]
    assert toolchains.install(paths, "node", VERSION, fetch=None) == final  # already there


def test_checksum_mismatch(paths, node_dist):
    (node_dist.dist / f"{STEM}.tar.xz").write_bytes(b"tampered")
    with pytest.raises(ToolchainError, match="does not match"):
        toolchains.install(paths, "node", VERSION, fetch=node_dist, arch="x64")
    assert not (paths.cache / "toolchains" / "node" / VERSION).exists()
    assert list((paths.cache / "toolchains" / "node").iterdir()) == []


def test_not_listed_in_shasums(paths, node_dist):
    (node_dist.dist / "SHASUMS256.txt").write_text("")
    with pytest.raises(ToolchainError, match="not listed"):
        toolchains.install(paths, "node", VERSION, fetch=node_dist, arch="x64")


def test_path_for_missing_names_the_install_command(paths):
    with pytest.raises(ToolchainError, match=r"mulebox toolchain install pnpm 11\.22\.0"):
        toolchains.path_for(paths, {"pnpm": "11.22.0"})
    assert toolchains.path_for(paths, {}) == []


@pytest.mark.parametrize("name,version", [("ruby", "3.3.0"), ("node", "latest"),
                                          ("node", "../../x"), ("node", "22")])
def test_bad_names_and_versions(paths, name, version):
    with pytest.raises(ToolchainError):
        toolchains.install(paths, name, version, fetch=None)


def test_pnpm_needs_node(paths):
    with pytest.raises(ToolchainError, match="needs a node toolchain"):
        toolchains.install(paths, "pnpm", "11.22.0", run=None)


def test_pnpm_install_uses_node_npm(paths, node_dist):
    node = toolchains.install(paths, "node", VERSION, fetch=node_dist, arch="x64")
    calls = []

    def run(argv, env):
        calls.append((argv, env))
        prefix = argv[argv.index("--prefix") + 1]
        (Path(prefix) / "bin").mkdir()
        (Path(prefix) / "bin" / "pnpm").write_text("#!/bin/sh\n")
        return subprocess.CompletedProcess(argv, 0, "", "")

    final = toolchains.install(paths, "pnpm", "11.22.0", run=run)
    argv, env = calls[0]
    assert argv[0] == str(node / "bin" / "npm")
    assert argv[1:4] == ["install", "-g", "--prefix"] and argv[-1] == "pnpm@11.22.0"
    assert env["PATH"].startswith(str(node / "bin"))
    assert (final / "bin" / "pnpm").exists()
    assert toolchains.installed(paths) == [("node", VERSION), ("pnpm", "11.22.0")]


def test_pnpm_install_failure(paths, node_dist):
    toolchains.install(paths, "node", VERSION, fetch=node_dist, arch="x64")
    run = lambda argv, env: subprocess.CompletedProcess(argv, 1, "", "E404")  # noqa: E731
    with pytest.raises(ToolchainError, match="E404"):
        toolchains.install(paths, "pnpm", "11.22.0", run=run)


def test_node_arch():
    assert toolchains.node_arch("x86_64") == "x64"
    assert toolchains.node_arch("aarch64") == "arm64"
    with pytest.raises(ToolchainError):
        toolchains.node_arch("sparc")
