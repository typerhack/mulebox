"""`mulebox init` for Apple platforms: an Xcode workspace or project, or a Swift package.

It runs on a Mac node (docs/install.md, macOS nodes). The Xcode is pinned to the one this
computer selects, as that is what builds it here today. A project whose targets build for iOS,
watchOS, tvOS or visionOS tests in a simulator of the job's own (`$MULEBOX_SIMULATOR`); one for
macOS alone on the Mac itself. Build products go to the job's own DerivedData folder and Swift
packages to the project's cache (worker/xcode.py, worker/caches.py).
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from mulebox.client.init_files import Detected, text
from mulebox.common import package_cache
from mulebox.common.config import SIMULATOR, XCODE
from mulebox.worker import xcode

# what a target builds for: `SDKROOT = iphoneos;`, or with `auto` its SUPPORTED_PLATFORMS
_SDK = re.compile(r"\b(?:SDKROOT|SUPPORTED_PLATFORMS) = \"?([\w ]+?)\"?;")
_SIMULATED = frozenset({"iphoneos", "watchos", "appletvos", "xros"})
_OTHER_PLATFORMS = {"watchos": "watchOS", "appletvos": "tvOS", "xros": "visionOS"}
# a project a workspace lists: `location = "group:App/App.xcodeproj"` (or container:)
_MEMBER = re.compile(r'location\s*=\s*"(?:group|container):([^"]+\.xcodeproj)"')
_SWIFT_TEST = 'swift test --cache-path "$MULEBOX_CACHE_SPM"'
_SPM = '-packageCachePath "$MULEBOX_CACHE_SPM"'
_DERIVED = '-derivedDataPath "$MULEBOX_DERIVED_DATA"'
_NO_SIGNING = "CODE_SIGNING_ALLOWED=NO"


def found_in(root: Path) -> bool:
    return (root / "Package.swift").is_file() or bool(_bundles(root, "xcworkspace")) \
        or bool(_bundles(root, "xcodeproj"))


def _bundles(root: Path, kind: str) -> list[Path]:
    return sorted(p for p in root.glob(f"*.{kind}") if p.is_dir())


def _schemes(bundle: Path) -> list[str]:
    """Shared schemes: the only ones a fresh checkout has (user schemes stay in xcuserdata)."""
    return sorted(p.stem for p in (bundle / "xcshareddata" / "xcschemes").glob("*.xcscheme"))


def _members(workspace: Path) -> list[Path]:
    """The projects a workspace lists, where they are."""
    listed = _MEMBER.findall(text(workspace / "contents.xcworkspacedata"))
    return [p for p in (workspace.parent / name for name in listed) if p.is_dir()]


def _sdks(projects: list[Path]) -> set[str]:
    return {sdk for project in projects
            for value in _SDK.findall(text(project / "project.pbxproj")) for sdk in value.split()}


def _pin_xcode(found: Detected) -> None:
    app = xcode.SELECTED()  # the one `xcode-select` points into (tests turn it off)
    read = xcode.version_of(app) if app is not None else None
    if read is None:
        found.notes.append("xcode: this computer has none selected, so none is pinned and the "
                           "node needs `toolchain: {xcode: ...}` with a version it has")
        return
    found.toolchain[XCODE] = read[0]
    found.notes.append(f"xcode: pinned {read[0]}, the one this computer selects; the Mac node "
                       "must have it, as a job never installs Xcode")


def apple(root: Path, found: Detected) -> None:
    workspaces, projects = _bundles(root, "xcworkspace"), _bundles(root, "xcodeproj")
    package = (root / "Package.swift").is_file()
    _pin_xcode(found)
    found.needs.append(package_cache.SPM)
    if (workspaces or projects) and _xcode_project(root, found, workspaces, projects):
        return
    if package:  # a package alone, or beside a project with no shared scheme
        found.jobs.setdefault("test", _SWIFT_TEST)
        found.checks.append(_SWIFT_TEST)
        found.notes.append("swift: a Swift package, tested with `swift test`; on a Mac node "
                           "that is Xcode's Swift")


def _xcode_project(root: Path, found: Detected, workspaces: list[Path],
                   projects: list[Path]) -> bool:
    """The job for a workspace or project; False when it has no shared scheme to test."""
    pods = (root / "Podfile").is_file()
    if workspaces:
        bundle, flag = workspaces[0], "-workspace"
        projects = list(dict.fromkeys([*_members(bundle), *projects]))
    elif pods:  # `pod install` makes the workspace, named after the project, and it must be used
        bundle, flag = root / f"{projects[0].stem}.xcworkspace", "-workspace"
    else:
        bundle, flag = projects[0], "-project"
    schemes = (_schemes(bundle) if bundle.is_dir() else []) or sorted(
        {s for p in projects for s in _schemes(p)})
    if pods:
        found.setup.append("pod install")
        found.needs.append(package_cache.COCOAPODS)
        found.notes.append("cocoapods: the Mac node must have `pod` on its PATH")
    if not schemes:
        found.notes.append(f"xcode: {bundle.name} has no shared scheme, so no test was found; "
                           "share one in Xcode (Product, Scheme, Manage Schemes, Shared)")
        return False
    scheme = next((s for s in schemes if s == bundle.stem), schemes[0])
    sdks = _sdks(projects) & _SIMULATED
    simulated = bool(sdks)
    destination = '"id=$MULEBOX_SIMULATOR"' if simulated else "platform=macOS"
    if simulated:
        found.needs.append(SIMULATOR)
    if sdks and "iphoneos" not in sdks:
        names = ", ".join(sorted(_OTHER_PLATFORMS[s] for s in sdks))
        found.notes.append(f"simulator: the targets build for {names}; pin its runtime, "
                           "`toolchain: {simulator: \"<name> <version>\"}` as `mulebox doctor` "
                           "lists them, as a job without a pin gets an iOS simulator")
    command = (f"xcodebuild test {flag} {shlex.quote(bundle.name)} -scheme "
               f"{shlex.quote(scheme)} -destination {destination} {_DERIVED} {_SPM} "
               f"{_NO_SIGNING}")
    found.jobs.setdefault("test", command)
    found.checks.append(command)
    found.notes.append(f"xcode: scheme {scheme} of {bundle.name}"
                       + (", in a simulator of the job's own" if simulated else ", on the Mac")
                       + (f"; other shared schemes: {', '.join(s for s in schemes if s != scheme)}"
                          if len(schemes) > 1 else "")
                       + "; the targets of every project decide simulator or Mac, so check "
                       "the destination fits that scheme")
    return True
