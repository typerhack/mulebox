"""Xcode on a macOS node: which ones are installed, what they hold, and the one a job pins.

A job pins one in `.mulebox.yml` as a toolchain, `toolchain: {xcode: "16.2"}`. mulebox does not
install Xcode (it is gigabytes, from the App Store or developer.apple.com behind an Apple account),
so a version the node lacks makes the job exit 5 before it starts, naming the versions it has, as a
pinned Node.js that cannot install does. The job gets `DEVELOPER_DIR` set to that Xcode's
`Contents/Developer`, which `xcodebuild`, `xcrun` and `swift` follow; the machine's own choice
(`xcode-select`) is left as it is.

Found: every `/Applications/Xcode*.app`, and the one `xcode-select -p` points into wherever it is,
each with its version from `Contents/version.plist` (`CFBundleShortVersionString`, the version
`xcodebuild -version` prints). What they hold, for `mulebox doctor`: each one's SDKs (`xcodebuild
-showsdks -json`) and the simulator runtimes (`xcrun simctl list runtimes --json`). Those take
seconds each, so the worker asks them beside its loop and gives its claims the last answer.

The worker reports them beside its toolchains (advert.py): `xcode` the versions, `xcode-sdk` the
SDKs (`iphoneos18.2`), `simulator` the available runtimes (`iOS 18.2`), from a scan beside its loop
every 5 minutes (Inventory); and the capability `xcode` while one is installed, which a project
that pins one needs, so only such a Mac claims its jobs, and `simulator` while a runtime is.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from mulebox.common import command
from mulebox.common.config import XCODE as NAME  # the toolchain, and the capability it gives
from mulebox.common.errors import MuleboxError
from mulebox.common.versions import same_release
from mulebox.worker import background, simulator

APPLICATIONS = Path("/Applications")
_VERSION = re.compile(r"\d{1,3}(\.\d{1,3}){0,2}")
_TIMEOUT_S = 60

Run = Callable[..., subprocess.CompletedProcess]  # command.run


class XcodeMissing(MuleboxError):
    """The Xcode a job pins is not on this node."""


@dataclass(frozen=True)
class Xcode:
    version: str
    app: Path
    build: str | None = None

    @property
    def developer_dir(self) -> Path:
        return self.app / "Contents" / "Developer"


def version_of(app: Path) -> tuple[str, str | None] | None:
    """(version, build) from an Xcode bundle's version.plist; None for anything else."""
    try:
        data = plistlib.loads((app / "Contents" / "version.plist").read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    version = data.get("CFBundleShortVersionString") if isinstance(data, dict) else None
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        return None
    build = data.get("ProductBuildVersion")
    return version, build if isinstance(build, str) else None


def selected_app(run: Run = command.run) -> Path | None:
    """The Xcode bundle `xcode-select -p` points into; None for the Command Line Tools."""
    try:
        done = run(["xcode-select", "-p"], timeout_s=10)
    except command.CommandError:
        return None
    path = Path(done.stdout.strip()) if done.returncode == 0 else None
    if path is None or path.parts[-2:] != ("Contents", "Developer"):
        return None
    return path.parent.parent


SELECTED = selected_app  # where installed() asks; tests turn it off


def installed(apps: Path | None = None, selected: Callable[[], Path | None] | None = None
              ) -> list[Xcode]:
    """Every Xcode found, oldest version first; of two with one version, the first by name."""
    apps = APPLICATIONS if apps is None else apps
    bundles = sorted(apps.glob("Xcode*.app")) if apps.is_dir() else []
    chosen = (selected or SELECTED)()
    if chosen is not None and chosen not in bundles:
        bundles.append(chosen)
    found: dict[str, Xcode] = {}
    for app in bundles:
        read = version_of(app)
        if read is not None and read[0] not in found:
            found[read[0]] = Xcode(read[0], app, read[1])
    return sorted(found.values(), key=lambda x: tuple(int(p) for p in x.version.split(".")))


def missing_reason(version: str, xcodes: list[Xcode]) -> str:
    have = ", ".join(x.version for x in xcodes)
    choice = (f"installed: {have}; pin one of them in .mulebox.yml" if have
              else "no Xcode is installed")
    return (f"Xcode {version} is not installed on this node ({choice}), or install it there as "
            f"/Applications/Xcode-{version}.app")


def pinned(toolchain: Mapping[str, str], xcodes: Callable[[], list[Xcode]] | None = None
           ) -> Xcode | None:
    """The Xcode a job's toolchain map pins (`16.2` is `16.2.0`); None when it pins none.
    XcodeMissing if absent. By default from the last scan (known), so a claim runs no
    `xcode-select`; a bundle removed since is missing too."""
    version = toolchain.get(NAME)
    if version is None:
        return None
    found = (xcodes or known)()
    for xcode in found:
        if same_release(xcode.version, version) and xcode.developer_dir.is_dir():
            return xcode
    raise XcodeMissing(missing_reason(version, found))


def env_for(toolchain: Mapping[str, str], xcodes: Callable[[], list[Xcode]] | None = None
            ) -> dict[str, str]:
    """`DEVELOPER_DIR` of the pinned Xcode, for the job's environment."""
    xcode = pinned(toolchain, xcodes)
    return {} if xcode is None else {"DEVELOPER_DIR": str(xcode.developer_dir)}


def parse_sdks(text: str) -> list[str]:
    """`canonicalName` of each SDK in `xcodebuild -showsdks -json`."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    return [sdk["canonicalName"] for sdk in data if isinstance(sdk, dict)
            and isinstance(sdk.get("canonicalName"), str)] if isinstance(data, list) else []


def _ask(argv: list[str], xcode: Xcode, run: Run) -> str:
    env = {**os.environ, "DEVELOPER_DIR": str(xcode.developer_dir)}
    try:
        done = run(argv, timeout_s=_TIMEOUT_S, env=env)
    except command.CommandError:
        return ""
    return done.stdout if done.returncode == 0 else ""


class Scan(dict):
    """What a scan reports ({name: [values]}, as advert.py sends it), with the Xcodes it found
    kept beside it for the jobs of this node: the Xcodes (pinned) and the simulator runtimes
    (simulator.py)."""

    xcodes: tuple[Xcode, ...] = ()
    runtimes: dict[str, tuple[simulator.Runtime, ...]] = {}  # by Xcode version


def scan(xcodes: Callable[[], list[Xcode]] | None = None, run: Run = command.run
         ) -> dict[str, list[str]]:
    """{`xcode`: versions, `xcode-sdk`: SDKs, `simulator`: runtimes}; {} with no Xcode. Slow:
    one `xcodebuild` and one `simctl` per Xcode, so the worker asks it beside its loop (report).
    Runtimes are asked of each Xcode, as an older one cannot use a newer runtime."""
    found = (xcodes or installed)()
    if not found:
        return {}
    sdks = sorted({sdk for x in found
                   for sdk in parse_sdks(_ask(["xcodebuild", "-showsdks", "-json"], x, run))})
    runtimes = {x.version: tuple(simulator.parse_runtimes(
        _ask(["xcrun", "simctl", "list", "runtimes", "--json"], x, run))) for x in found}
    done = Scan({NAME: [x.version for x in found], "xcode-sdk": sdks,
                 "simulator": sorted({r.name for each in runtimes.values() for r in each})})
    done.xcodes, done.runtimes = tuple(found), runtimes
    return done


class Inventory:
    """The last finished scan, asked again beside the worker's loop every `REFRESH_S`: a
    runtime installed or removed, an Xcode added, or a probe that failed shows up by then.
    {} until the first scan ends, so a Mac offers `xcode` from its second claim on."""

    REFRESH_S = 300.0

    def __init__(self, ask: Callable[[], dict[str, list[str]]] = scan,
                 clock: Callable[[], float] = time.monotonic,
                 start: Callable[[Callable[[], None]], object] = background.start_thread) -> None:
        self._ask, self._clock, self._start = ask, clock, start
        self._found: dict[str, list[str]] = {}
        self._asked_at: float | None = None
        self._running = False

    def _run(self) -> None:
        try:
            self._found = self._ask()
        finally:
            self._running = False

    def value(self) -> dict[str, list[str]]:
        now = self._clock()
        if not self._running and (self._asked_at is None
                                  or now - self._asked_at >= self.REFRESH_S):
            self._asked_at, self._running = now, True
            self._start(self._run)
        return self._found

    def xcodes(self) -> list[Xcode]:
        """The Xcodes of the last finished scan; none before it."""
        return list(getattr(self._found, "xcodes", ()))

    def runtimes(self, version: str | None = None) -> list[simulator.Runtime]:
        """The simulator runtimes the Xcode `version` (None: the newest) can use, from the
        last finished scan; none before it."""
        xcodes = self.xcodes()
        chosen = next((x for x in xcodes if version and same_release(x.version, version)),
                      None if version else (xcodes[-1] if xcodes else None))
        by_xcode = getattr(self._found, "runtimes", {})
        return list(by_xcode.get(chosen.version, ())) if chosen is not None else []


_INVENTORY: Inventory | None = None


def _inventory() -> Inventory:
    global _INVENTORY
    if _INVENTORY is None:
        _INVENTORY = Inventory()
    return _INVENTORY


def report() -> dict[str, list[str]]:
    """This Mac's Xcodes for the worker's claims, never waiting on a scan (Inventory)."""
    return _inventory().value()


def known() -> list[Xcode]:
    """The Xcodes a job can pin: the last scan's, or, before one has finished, a look now
    (a node offers `xcode` only after its first scan, so a job rarely gets here)."""
    return _inventory().xcodes() or installed()


def runtimes(version: str | None = None) -> list[simulator.Runtime]:
    """The simulator runtimes a job pinning Xcode `version` (None: the newest Xcode) can have,
    from the last scan (a node offers `simulator` only once a scan found one)."""
    return _inventory().runtimes(version)


def newest_developer_dir() -> str | None:
    """The newest Xcode's `Contents/Developer`, for a job that pins none; None with no
    Xcode."""
    found = known()
    return str(found[-1].developer_dir) if found else None


def simulators(platform: str = sys.platform) -> simulator.Simulators | None:
    """What removes jobs' simulators, on a Mac; None elsewhere."""
    return simulator.Simulators(newest_developer_dir) if platform == "darwin" else None
