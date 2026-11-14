"""A simulator of its own for each job that asks for one, on a macOS node with Xcode.

A project asks with `needs: [simulator]`, or pins the runtime, `toolchain: {simulator:
"iOS 18.2"}`; without a pin it gets the newest iOS runtime the node has. Its device is the
newest iPhone that runtime supports, or for another platform (watchOS, tvOS, visionOS) the
newest device of it. The runtime and device are chosen from the worker's last Xcode scan
(xcode.Inventory), of the runtimes the job's Xcode (pinned, else the newest) can use, so nothing
slow runs in the worker's loop; a pinned runtime the node lacks
makes the job exit 5 before it starts, naming the runtimes it has.

The job's script creates it, as its first lines (`xcrun simctl create`), so a slow or stuck
CoreSimulator holds up that job only, and a cancel stops it. Its id is `$MULEBOX_SIMULATOR`, for
`xcodebuild test -destination "id=$MULEBOX_SIMULATOR"`; it is not booted, as xcodebuild boots
it. It is named `mulebox-<job id>` and removed by that name when the job is cleaned up, on every
outcome; a worker that starts removes every `mulebox-job-...` simulator an earlier one left.
Simulators live in the user's default device set (`~/Library/Developer/CoreSimulator`), the only
one xcodebuild uses, so they are made and removed through `simctl`, never as files, and only
those with mulebox's own names.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from mulebox.common import command
from mulebox.common.config import SIMULATOR as NAME  # the capability, and the toolchain pin
from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.versions import same_release

LOG = get_logger("worker.simulator")
PREFIX = "mulebox-"
_JOB_NAME = re.compile(r"mulebox-job-[0-9A-Za-z]{1,64}")
_TIMEOUT_S = 60
DEFAULT_PLATFORM = "iOS"
_FAMILY = {"iOS": "iPhone"}  # of a runtime's devices, the kind a job gets

Run = Callable[..., object]  # command.run


class SimulatorMissing(MuleboxError):
    """The runtime a job pins, or any runtime, is not on this node."""


@dataclass(frozen=True)
class Runtime:
    name: str  # "iOS 18.2", as the worker reports it and a project pins it
    identifier: str  # com.apple.CoreSimulator.SimRuntime.iOS-18-2
    platform: str
    version: str
    devices: tuple[tuple[str, str], ...]  # (device type identifier, product family), newest first

    @property
    def order(self) -> tuple[int, ...]:
        return tuple(int(p) for p in re.findall(r"\d+", self.version))


def parse_runtimes(text: str) -> list[Runtime]:
    """The available runtimes in `xcrun simctl list runtimes --json`."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    found = []
    for item in (data.get("runtimes") if isinstance(data, dict) else None) or []:
        if not isinstance(item, dict) or not item.get("isAvailable"):
            continue
        fields = [item.get(key) for key in ("name", "identifier", "platform", "version")]
        if not all(isinstance(value, str) for value in fields):
            continue
        devices = tuple((d["identifier"], str(d.get("productFamily") or ""))
                        for d in item.get("supportedDeviceTypes") or []
                        if isinstance(d, dict) and isinstance(d.get("identifier"), str))
        found.append(Runtime(*fields, devices))
    return found


def choose(runtimes: Sequence[Runtime], pinned: str | None) -> tuple[Runtime, str]:
    """(runtime, device type) for a job; SimulatorMissing when it cannot have one."""
    usable = [r for r in runtimes if r.devices]
    if pinned is not None:
        picked = [r for r in usable if same_release(r.name, pinned)]
    else:
        picked = sorted((r for r in usable if r.platform == DEFAULT_PLATFORM),
                        key=lambda r: r.order)[-1:]
    if not picked:
        have = ", ".join(sorted(r.name for r in usable)) or "none"
        wanted = f"the simulator runtime {pinned}" if pinned else f"an {DEFAULT_PLATFORM} runtime"
        raise SimulatorMissing(f"this node has no {wanted} (runtimes: {have}); install one with "
                               "Xcode (Settings, Components) or `xcodebuild -downloadPlatform "
                               f"{DEFAULT_PLATFORM}`, or pin one it has")
    runtime = picked[-1]
    family = _FAMILY.get(runtime.platform)
    kinds = [d for d, f in runtime.devices if f == family] or [d for d, _ in runtime.devices]
    return runtime, max(kinds, key=_model)  # the first of the highest model number


def _model(device_type: str) -> int:
    """The model number in a device type's id (`iPhone-16-Pro` 16), 0 for none (`iPhone-XS`).
    simctl's order is not the newest first, so this picks the newest."""
    found = re.search(r"\.[A-Za-z-]*?-(\d+)(?:-|$)", device_type)
    return int(found[1]) if found else 0


def device_name(job_id: str) -> str:
    return f"{PREFIX}{job_id}"


def script_lines(job_id: str, runtime: Runtime, device_type: str,
                 developer_dir: str | None = None) -> tuple[str, ...]:
    """The job script's first lines: make the simulator and export its id."""
    argv = ["xcrun", "simctl", "create", device_name(job_id), device_type, runtime.identifier]
    if developer_dir is not None:
        argv = ["env", f"DEVELOPER_DIR={developer_dir}", *argv]
    return (f"echo {shlex.quote(f'mulebox: a simulator of its own, {runtime.name}')}",
            f"MULEBOX_SIMULATOR=$({shlex.join(argv)})",
            "export MULEBOX_SIMULATOR")


def wanted(claim: Mapping[str, object]) -> bool:
    """Whether a claimed job asks for a simulator: `needs: [simulator]`, or a runtime pinned."""
    needs, toolchain = claim.get("needs") or (), claim.get("toolchain") or {}
    return NAME in needs or (isinstance(toolchain, Mapping) and NAME in toolchain)


def for_job(claim: Mapping[str, object], runtimes: Sequence[Runtime], job_id: str,
            developer_dir: str | None = None) -> tuple[str, ...]:
    """Script lines for a job that asks for a simulator; () for any other. `developer_dir`:
    the Xcode whose `simctl` makes it, when the job pins none (then its own is used)."""
    if not wanted(claim):
        return ()
    toolchain = claim.get("toolchain") or {}
    runtime, device_type = choose(runtimes, toolchain.get(NAME))  # type: ignore[union-attr]
    return script_lines(job_id, runtime, device_type, developer_dir)


def parse_devices(text: str) -> list[tuple[str, str]]:
    """(udid, name) of every device in `xcrun simctl list devices --json`. An answer it cannot
    read is an error, never an empty list: that would count as removed (cleaner.py)."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise MuleboxError(f"`xcrun simctl list devices` gave no JSON: {exc}") from exc
    groups = data.get("devices") if isinstance(data, dict) else None
    if not isinstance(groups, dict):
        raise MuleboxError("`xcrun simctl list devices` gave no device list")
    return [(d["udid"], d["name"]) for group in (groups or {}).values()
            if isinstance(group, list) for d in group
            if isinstance(d, dict) and isinstance(d.get("udid"), str)
            and isinstance(d.get("name"), str)]


class Simulators:
    """Removing the simulators of jobs, through `simctl` of the given Xcode (None: there is
    none, so nothing to remove)."""

    def __init__(self, developer_dir: Callable[[], str | None], run: Run = command.run) -> None:
        self._developer_dir, self._run = developer_dir, run

    def _simctl(self, *args: str):
        env = {**os.environ, "DEVELOPER_DIR": str(self._developer_dir())}
        return self._run(["xcrun", "simctl", *args], timeout_s=_TIMEOUT_S, env=env)

    def _named(self, wanted: Callable[[str], bool]) -> list[str]:
        if self._developer_dir() is None:
            return []  # no Xcode, so no simulator either
        done = self._simctl("list", "devices", "--json")
        if done.returncode != 0:
            raise MuleboxError(f"`xcrun simctl list devices` failed: {done.stderr.strip()[-200:]}")
        return [udid for udid, name in parse_devices(done.stdout) if wanted(name)]

    def _delete(self, udid: str) -> None:
        self._simctl("shutdown", udid)  # one that is not booted says so; that is fine
        done = self._simctl("delete", udid)
        if done.returncode != 0:
            raise MuleboxError(f"`xcrun simctl delete {udid}` failed: "
                               f"{done.stderr.strip()[-200:]}")

    def remove(self, job_id: str) -> int:
        """Remove the job's simulator; MuleboxError means try again."""
        udids = self._named(lambda name: name == device_name(job_id))
        for udid in udids:
            self._delete(udid)
        return len(udids)

    def remove_leftovers(self) -> int:
        """Remove every job simulator; for a worker that starts, when none of its jobs runs."""
        udids = self._named(lambda name: _JOB_NAME.fullmatch(name) is not None)
        for udid in udids:
            self._delete(udid)
        if udids:
            LOG.info("removed %d simulator%s earlier jobs left", len(udids),
                     "" if len(udids) == 1 else "s")
        return len(udids)
