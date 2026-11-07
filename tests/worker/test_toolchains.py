"""Toolchains: verified node install, pnpm through node's npm, clear errors. No network."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from mulebox.worker import toolchains
from mulebox.worker.toolchains import ToolchainError, ToolchainNetwork

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


def test_missing_version_lists_what_the_machine_has(paths):
    for version in ("22.9.0", "20.18.1"):
        (toolchains.toolchain_dir(paths, "node", version) / "bin").mkdir(parents=True)
    with pytest.raises(toolchains.ToolchainError) as caught:
        toolchains.path_for(paths, {"node": "22.22.3"})
    text = str(caught.value)
    assert "installed node versions: 20.18.1, 22.9.0;" in text
    assert "mulebox toolchain install node 22.22.3" in text


def test_missing_with_nothing_installed_says_so(paths):
    with pytest.raises(toolchains.ToolchainError, match="no pnpm version is installed"):
        toolchains.path_for(paths, {"pnpm": "11.22.0"})


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


def test_missing_is_what_is_not_there_node_first(paths):
    wanted = {"pnpm": "11.22.0", "node": "22.22.3"}
    assert toolchains.missing(paths, wanted) == [("node", "22.22.3"), ("pnpm", "11.22.0")]
    (paths.toolchains_dir() / "node" / "22.22.3" / "bin").mkdir(parents=True)
    assert toolchains.missing(paths, wanted) == [("pnpm", "11.22.0")]


def test_a_failed_install_says_why_and_what_is_here(paths):
    (paths.toolchains_dir() / "node" / "20.18.1" / "bin").mkdir(parents=True)

    def offline(paths, name, version):
        raise OSError("no route")

    with pytest.raises(toolchains.ToolchainError, match="no route.*20.18.1"):
        toolchains.install_missing(paths, [("node", "22.22.3")], offline)


def test_a_machines_job_env_reaches_the_install(paths):
    (paths.toolchains_dir() / "node" / "22.22.3" / "bin").mkdir(parents=True)
    seen = {}

    def run(argv, env):
        seen.update(env)
        return subprocess.CompletedProcess(argv, 1, "", "stop here")

    with pytest.raises(toolchains.ToolchainError):
        toolchains.install(paths, "pnpm", "11.22.0", run=run,
                           machine_env={"NODE_OPTIONS": "--example"})
    assert seen["NODE_OPTIONS"] == "--example"


def test_a_lost_network_is_tried_again(paths, node_dist):
    waits, lost = [], ["a", "b"]

    def flaky(url, dest):
        if lost:
            lost.pop()
            raise ToolchainNetwork("connection reset")
        node_dist(url, dest)

    final = toolchains.install(paths, "node", VERSION, fetch=flaky, arch="x64", sleep=waits.append)
    assert (final / "bin").is_dir() and waits == [5, 10]


def test_a_network_that_stays_lost_says_so_and_offers_no_other_version(paths):
    def down(url, dest):
        raise ToolchainNetwork("connection reset")

    def install_one(paths, name, version):
        return toolchains.install(paths, name, version, fetch=down, arch="x64", sleep=lambda _: None)

    with pytest.raises(ToolchainNetwork) as found:
        toolchains.install_missing(paths, [("node", VERSION)], install_one)
    assert "lost its network" in str(found.value) and "use one of them" not in str(found.value)
    assert not (paths.toolchains_dir() / "node" / VERSION).exists()


def test_a_version_that_does_not_exist_is_not_tried_again(paths):
    calls = []

    def missing(url, dest):
        calls.append(url)
        raise ToolchainError("HTTP Error 404")

    with pytest.raises(ToolchainError):
        toolchains.install(paths, "node", VERSION, fetch=missing, arch="x64", sleep=calls.append)
    assert len(calls) == 1
