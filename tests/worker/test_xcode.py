"""Xcode as a toolchain (worker/xcode.py): found, reported, pinned. Bundles are folders made
here; the answers of xcodebuild and simctl are shaped as a real Mac gives them."""

import json
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from mulebox.client import doctor
from mulebox.common.config import ProjectConfig
from mulebox.worker import advert, simulator, toolchains, xcode

SDKS = json.dumps([
    {"canonicalName": "iphoneos27.2", "displayName": "iOS 27.2", "platform": "iphoneos",
     "sdkVersion": "27.2"},
    {"canonicalName": "iphonesimulator27.2", "platform": "iphonesimulator", "sdkVersion": "27.2"},
    {"canonicalName": "macosx27.2", "platform": "macosx", "sdkVersion": "27.2"},
])
RUNTIMES = json.dumps({"runtimes": [
    {"isAvailable": True, "version": "26.0", "name": "iOS 26.0", "platform": "iOS",
     "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-0", "supportedDeviceTypes": []},
    {"isAvailable": False, "version": "17.0", "name": "iOS 17.0", "platform": "iOS"},
]})


def bundle(apps: Path, name: str, version: str, build: str = "27B52") -> Path:
    app = apps / name
    (app / "Contents" / "Developer").mkdir(parents=True)
    (app / "Contents" / "version.plist").write_bytes(plistlib.dumps(
        {"CFBundleShortVersionString": version, "ProductBuildVersion": build}))
    return app


def found(apps, selected=None):
    return lambda: xcode.installed(apps, lambda: selected)


def test_every_xcode_is_found_oldest_first_with_the_selected_one(tmp_path):
    apps = tmp_path / "Applications"
    bundle(apps, "Xcode.app", "27.2")
    bundle(apps, "Xcode-16.4.app", "16.4")
    bundle(apps, "Xcode_copy.app", "27.2")  # the same version twice: the first by name is kept
    (apps / "Xcode-broken.app").mkdir()
    elsewhere = bundle(tmp_path / "home" / "Applications", "Xcode-beta.app", "28.0")
    xcodes = xcode.installed(apps, lambda: elsewhere)
    assert [(x.version, x.app.name) for x in xcodes] == [
        ("16.4", "Xcode-16.4.app"), ("27.2", "Xcode.app"), ("28.0", "Xcode-beta.app")]
    assert xcodes[0].developer_dir == apps / "Xcode-16.4.app" / "Contents" / "Developer"
    assert xcode.installed(tmp_path / "none", lambda: None) == []


def test_the_selected_app_comes_from_xcode_select():
    def run(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, "/Applications/Xcode.app/Contents/Developer\n")

    def tools(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, "/Library/Developer/CommandLineTools\n")

    assert xcode.selected_app(run) == Path("/Applications/Xcode.app")
    assert xcode.selected_app(tools) is None  # the Command Line Tools are no Xcode


def test_a_pinned_xcode_sets_developer_dir_and_a_missing_one_names_what_is_there(tmp_path):
    apps = tmp_path / "Applications"
    bundle(apps, "Xcode.app", "27.2")
    assert xcode.env_for({"xcode": "27.2"}, found(apps)) == {
        "DEVELOPER_DIR": str(apps / "Xcode.app" / "Contents" / "Developer")}
    assert xcode.env_for({"node": "22.22.3"}, found(apps)) == {}
    with pytest.raises(xcode.XcodeMissing, match=r"Xcode 16\.2 is not installed.*installed: 27\.2"):
        xcode.pinned({"xcode": "16.2"}, found(apps))
    with pytest.raises(xcode.XcodeMissing, match="no Xcode is installed"):
        xcode.pinned({"xcode": "16.2"}, found(tmp_path / "none"))


def test_a_missing_xcode_stops_the_job_before_any_install(tmp_path, monkeypatch, paths):
    monkeypatch.setattr(xcode, "APPLICATIONS", tmp_path / "Applications")
    bundle(tmp_path / "Applications", "Xcode.app", "27.2")
    with pytest.raises(xcode.XcodeMissing):
        toolchains.missing(paths, {"xcode": "16.2", "node": "22.22.3"})
    assert toolchains.missing(paths, {"xcode": "27.2"}) == []  # nothing to install for it
    assert toolchains.path_for(paths, {"xcode": "27.2"}) == []


def test_the_scan_lists_versions_sdks_and_available_runtimes(tmp_path):
    apps = tmp_path / "Applications"
    bundle(apps, "Xcode.app", "27.2")
    bundle(apps, "Xcode-16.4.app", "16.4")
    asked = []

    def run(argv, timeout_s=None, env=None):
        asked.append((argv[0], Path(env["DEVELOPER_DIR"]).parent.parent.name))
        return subprocess.CompletedProcess(argv, 0, SDKS if argv[0] == "xcodebuild" else RUNTIMES)

    assert xcode.scan(found(apps), run) == {
        "xcode": ["16.4", "27.2"],
        "xcode-sdk": ["iphoneos27.2", "iphonesimulator27.2", "macosx27.2"],
        "simulator": ["iOS 26.0"]}
    assert asked == [("xcodebuild", "Xcode-16.4.app"), ("xcodebuild", "Xcode.app"),
                     ("xcrun", "Xcode.app")]  # runtimes from the newest
    assert xcode.scan(found(tmp_path / "none"), run) == {}


def test_the_inventory_never_waits_and_is_asked_again_every_few_minutes():
    clock, answers, started = [0.0], [{"xcode": ["16.4"]}, {"xcode": ["16.4", "27.2"]}], []
    inventory = xcode.Inventory(ask=lambda: answers.pop(0), clock=lambda: clock[0],
                                start=started.append)
    assert inventory.value() == {} and len(started) == 1  # the first scan runs beside the loop
    assert inventory.value() == {} and len(started) == 1  # one at a time
    started[0]()
    assert inventory.value() == {"xcode": ["16.4"]} and len(started) == 1
    clock[0] = xcode.Inventory.REFRESH_S
    assert inventory.value() == {"xcode": ["16.4"]} and len(started) == 2  # last answer kept
    started[1]()
    assert inventory.value() == {"xcode": ["16.4", "27.2"]}


def test_a_failed_scan_keeps_the_last_answer_and_is_tried_again():
    clock, calls = [0.0], []

    def ask():
        calls.append(1)
        if len(calls) == 2:
            raise OSError("simctl crashed")
        return {"xcode": ["27.2"]}

    def start(work):
        try:
            work()
        except OSError:
            pass  # a thread's error goes nowhere (background.Task)

    inventory = xcode.Inventory(ask=ask, clock=lambda: clock[0], start=start)
    assert inventory.value() == {"xcode": ["27.2"]}
    clock[0] = xcode.Inventory.REFRESH_S
    assert inventory.value() == {"xcode": ["27.2"]}  # the failure kept the last answer
    clock[0] = 2 * xcode.Inventory.REFRESH_S
    assert inventory.value() == {"xcode": ["27.2"]} and len(calls) == 3  # and was asked again


def test_unreadable_answers_give_nothing():
    assert xcode.parse_sdks("not json") == [] and xcode.parse_sdks('{"a": 1}') == []
    assert simulator.parse_runtimes("[]") == [] and simulator.parse_runtimes("x") == []


def test_a_mac_with_xcode_offers_it_and_a_project_pinning_one_needs_it(monkeypatch, paths):
    monkeypatch.setattr(xcode, "report", lambda: {"xcode": ["27.2"], "simulator": ["iOS 26.0"]})
    tools = advert.by_name(paths, platform="darwin")
    assert tools["xcode"] == ["27.2"] and advert.by_name(paths, platform="linux") == {}
    assert "xcode" in ProjectConfig(project="app", jobs={"t": "x"},
                                    toolchain={"xcode": "27.2"}).all_needs
    assert "xcode" not in ProjectConfig(project="app", jobs={"t": "x"}).all_needs


def test_doctor_says_a_missing_xcode_is_not_installed_by_a_job():
    project = ProjectConfig(project="app", jobs={"t": "x"}, toolchain={"xcode": "16.2"})
    mac = {"worker": "mac-1", "online": True, "capabilities": ["xcode"],
           "toolchains": {"xcode": ["27.2"]}, "version": "1.0.0"}
    [found] = doctor.machines(project, [mac])
    assert found.level == "fail" and "mac-1 has 27.2" in found.text and "exit 5" in found.text
    has = {**mac, "toolchains": {"xcode": ["16.2", "27.2"], "xcode-sdk": ["iphoneos16.2"],
                                 "simulator": ["iOS 18.2"]}}
    ok = doctor.machines(project, [has])
    assert [f.level for f in ok] == ["ok", "ok"] and "xcode 16.2" in ok[0].text
    assert ok[1].text == "mac-1: Xcode 16.2, 27.2; SDKs iphoneos16.2; simulators iOS 18.2"
    assert doctor.inventory([has])[1].text == ok[1].text  # outside a project too
    linux = {**mac, "worker": "build-1", "capabilities": ["docker"], "toolchains": {}}
    [none] = doctor.machines(project, [linux])
    assert none.level == "fail" and "Mac node with Xcode" in none.text


@pytest.mark.skipif(sys.platform != "darwin", reason="needs a Mac")
def test_this_macs_own_xcodes_are_read():
    xcodes = xcode.installed(Path("/Applications"), lambda: None)
    if not xcodes:
        pytest.skip("no Xcode in /Applications")
    assert all(x.developer_dir.is_dir() for x in xcodes)


def test_a_pin_matches_with_trailing_zeros_and_comes_from_the_last_scan(tmp_path, monkeypatch):
    apps = tmp_path / "Applications"
    app = bundle(apps, "Xcode.app", "27.2")
    assert xcode.pinned({"xcode": "27.2.0"}, found(apps)).app == app
    with pytest.raises(xcode.XcodeMissing):
        xcode.pinned({"xcode": "27.20"}, found(apps))
    done = xcode.Scan({"xcode": ["27.2"]})
    done.xcodes = (xcode.Xcode("27.2", app),)
    monkeypatch.setattr(xcode, "_INVENTORY", xcode.Inventory(ask=lambda: done,
                                                             start=lambda work: work()))
    monkeypatch.setattr(xcode, "installed", lambda *a: pytest.fail("probed during a claim"))
    xcode.report()
    assert xcode.env_for({"xcode": "27.2"}) == {"DEVELOPER_DIR": str(app / "Contents/Developer")}
    (app / "Contents" / "Developer").rmdir()  # removed since the scan
    with pytest.raises(xcode.XcodeMissing):
        xcode.pinned({"xcode": "27.2"})


def test_doctor_takes_a_pin_written_long():
    project = ProjectConfig(project="app", jobs={"t": "x"}, toolchain={"xcode": "16.2.0"})
    mac = {"worker": "mac-1", "online": True, "capabilities": ["xcode"],
           "toolchains": {"xcode": ["16.2"]}, "version": "1.0.0"}
    assert doctor.machines(project, [mac])[0].level == "ok"
