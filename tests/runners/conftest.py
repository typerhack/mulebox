"""Fixtures for runner management: a fake home with mulebox roots, a fake runner release,
and recording doubles for config.sh and systemctl. Nothing touches the network, GitHub or
the real systemd."""

import hashlib
import io
import subprocess
import tarfile
from pathlib import Path

import pytest

from mulebox.runners.manage import Machine
from mulebox.services.systemd import SystemdServices
from mulebox.worker.paths import NodePaths

TOKEN = "AABBCCDDEEFFGGHHIIJJKKLLMM0"  # shaped like a registration token
VERSION = "2.321.0"
ROOT_KEYS = ("jobs", "cache", "staging", "runners")


def make_tar(path: Path, files: dict[str, str]) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for name, text in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(text.encode()), 0o755
            tar.addfile(info, io.BytesIO(text.encode()))
    return path


def release_body(sha_x64: str, sha_arm64: str) -> str:
    """A release body in the layout actions/runner publishes."""
    return f"""## What's Changed
* Bump dependencies by @example in https://github.com/actions/runner/pull/1

## Linux x64

```bash
# Create a folder
$ mkdir actions-runner && cd actions-runner
# Download the latest runner package
$ curl -O -L https://github.com/actions/runner/releases/download/v{VERSION}/actions-runner-linux-x64-{VERSION}.tar.gz
# Extract the installer
$ tar xzf ./actions-runner-linux-x64-{VERSION}.tar.gz
```

## SHA-256 Checksums

The SHA-256 checksums for the packages included in this build are shown below:

- actions-runner-win-x64-{VERSION}.zip <!-- BEGIN SHA win-x64 -->{"1" * 64}<!-- END SHA win-x64 -->
- actions-runner-osx-x64-{VERSION}.tar.gz <!-- BEGIN SHA osx-x64 -->{"2" * 64}<!-- END SHA osx-x64 -->
- actions-runner-linux-x64-{VERSION}.tar.gz <!-- BEGIN SHA linux-x64 -->{sha_x64}<!-- END SHA linux-x64 -->
- actions-runner-linux-arm64-{VERSION}.tar.gz <!-- BEGIN SHA linux-arm64 -->{sha_arm64}<!-- END SHA linux-arm64 -->
- actions-runner-linux-x64-{VERSION}-noexternals.tar.gz <!-- BEGIN SHA linux-x64_noexternals -->{"3" * 64}<!-- END SHA linux-x64_noexternals -->
"""


def release_json(sha_x64: str, sha_arm64: str = "4" * 64) -> dict:
    base = f"https://github.com/actions/runner/releases/download/v{VERSION}"
    names = [f"actions-runner-{p}-{VERSION}.tar.gz" for p in ("osx-x64", "linux-x64",
                                                               "linux-arm64")]
    return {
        "tag_name": f"v{VERSION}",
        "name": f"v{VERSION}",
        "body": release_body(sha_x64, sha_arm64),
        "assets": [{"name": n, "browser_download_url": f"{base}/{n}", "size": 1}
                   for n in names],
    }


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    for key in ROOT_KEYS:
        (home / ".mulebox" / key).mkdir(parents=True)
    units = home / ".config" / "systemd" / "user"
    units.mkdir(parents=True)
    (units / "mulebox-runner@.service").write_text("[Service]\n")
    return home


@pytest.fixture
def paths(home):
    return NodePaths.from_config({k: str(home / ".mulebox" / k) for k in ROOT_KEYS})


@pytest.fixture
def tarball(tmp_path):
    (tmp_path / "dist").mkdir()
    return make_tar(tmp_path / "dist" / "runner.tar.gz", {
        "./config.sh": "#!/bin/bash\necho config\n",
        "./run.sh": "#!/bin/bash\necho run\n",
        "./bin/Runner.Listener": "binary",
    })


class Fakes:
    def __init__(self, tarball: Path) -> None:
        self.tarball = tarball
        self.sha = hashlib.sha256(tarball.read_bytes()).hexdigest()
        self.downloads: list[str] = []
        self.configs: list[tuple[list[str], Path, dict]] = []
        self.systemctl_calls: list[list[str]] = []
        self.config_result = (0, "", "")
        self.systemctl_codes: dict[str, int] = {}
        self.said: list[str] = []

    def fetch_json(self, url):
        self.downloads.append(url)
        return release_json(self.sha)

    def fetch_file(self, url, dest):
        self.downloads.append(url)
        with open(dest, "xb") as fh:
            fh.write(self.tarball.read_bytes())

    def config_run(self, argv, cwd, env):
        self.configs.append((list(argv), cwd, dict(env)))
        code, out, err = self.config_result
        if code == 0 and argv[1:2] != ["remove"]:
            (cwd / ".runner").write_text('{"agentName": "x"}')
            (cwd / ".env").write_text("LANG=C.UTF-8\nACTIONS_RUNNER_HOOK_JOB_STARTED=/old\n")
        return subprocess.CompletedProcess(argv, code, out, err)

    def systemctl(self, argv):
        self.systemctl_calls.append(list(argv))
        code = self.systemctl_codes.get(argv[2], 0)
        return subprocess.CompletedProcess(argv, code, "", "unit failed" if code else "")


@pytest.fixture
def fakes(tarball):
    return Fakes(tarball)


@pytest.fixture
def machine(paths, home, fakes):
    return Machine(paths, "build-1", config_run=fakes.config_run,
                   services=SystemdServices(home=home, run=fakes.systemctl), arch="x64",
                   system="linux", fetch_json=fakes.fetch_json, fetch_file=fakes.fetch_file,
                   say=fakes.said.append)
