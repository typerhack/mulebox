"""A simulator of its own per job (worker/simulator.py). simctl's answers are shaped as a real
Mac gives them; a stand-in records what would run."""

import json
import subprocess

import pytest

from mulebox.common.errors import MuleboxError
from mulebox.worker import jobspec, simulator

IPHONE_17 = "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro"
IPHONE_16 = "com.apple.CoreSimulator.SimDeviceType.iPhone-16"
IPHONE_XS = "com.apple.CoreSimulator.SimDeviceType.iPhone-XS"
IPAD = "com.apple.CoreSimulator.SimDeviceType.iPad-Air-11-inch-M3"
WATCH = "com.apple.CoreSimulator.SimDeviceType.Apple-Watch-Series-11-46mm"


def runtime(name, platform, version, devices, available=True):
    return {"isAvailable": available, "name": name, "platform": platform, "version": version,
            "identifier": f"com.apple.CoreSimulator.SimRuntime.{name.replace(' ', '-')}",
            "supportedDeviceTypes": [{"identifier": i, "productFamily": f, "name": i}
                                     for i, f in devices]}


RUNTIMES = json.dumps({"runtimes": [
    # simctl's order is not the newest first: an iPhone XS can come before an iPhone 16
    runtime("iOS 18.3", "iOS", "18.3.1", [(IPAD, "iPad"), (IPHONE_XS, "iPhone"),
                                          (IPHONE_16, "iPhone")]),
    runtime("iOS 26.0", "iOS", "26.0", [(IPAD, "iPad"), (IPHONE_16, "iPhone"),
                                        (IPHONE_17, "iPhone")]),
    runtime("watchOS 26.0", "watchOS", "26.0", [(WATCH, "Apple Watch")]),
    runtime("iOS 17.0", "iOS", "17.0", [(IPHONE_16, "iPhone")], available=False),
    {"name": "broken"},
]})


def test_the_newest_ios_runtime_and_its_newest_iphone_by_default():
    runtimes = simulator.parse_runtimes(RUNTIMES)
    assert [r.name for r in runtimes] == ["iOS 18.3", "iOS 26.0", "watchOS 26.0"]
    chosen, device = simulator.choose(runtimes, None)
    assert (chosen.name, device) == ("iOS 26.0", IPHONE_17)
    chosen, device = simulator.choose(runtimes, "iOS 18.3")
    assert (chosen.name, device) == ("iOS 18.3", IPHONE_16)
    chosen, device = simulator.choose(runtimes, "watchOS 26.0")  # another platform: its newest
    assert device == WATCH
    assert simulator.parse_runtimes("not json") == []


def test_a_runtime_the_node_lacks_names_the_ones_it_has():
    runtimes = simulator.parse_runtimes(RUNTIMES)
    with pytest.raises(simulator.SimulatorMissing,
                       match=r"runtime iOS 17\.0 \(runtimes: iOS 18\.3, iOS 26\.0, watchOS 26\.0\)"):
        simulator.choose(runtimes, "iOS 17.0")  # there, but not available
    with pytest.raises(simulator.SimulatorMissing, match=r"no an? iOS runtime \(runtimes: none\)"):
        simulator.choose([], None)


def test_the_script_makes_it_first_and_exports_its_id():
    runtimes = simulator.parse_runtimes(RUNTIMES)
    assert simulator.for_job({"needs": ["cache-spm"]}, runtimes, "job-01ABC") == ()
    lines = simulator.for_job({"needs": ["simulator"], "toolchain": {"xcode": "27.2"}},
                              runtimes, "job-01ABC")
    assert lines[1] == ("MULEBOX_SIMULATOR=$(xcrun simctl create mulebox-job-01ABC "
                        f"{IPHONE_17} com.apple.CoreSimulator.SimRuntime.iOS-26.0)")
    pinned = simulator.for_job({"toolchain": {"simulator": "iOS 18.3.0"}}, runtimes,
                               "job-01ABC", "/Applications/Xcode.app/Contents/Developer")
    assert "iOS-18.3" in pinned[1]  # a pin alone asks for one, written long or short
    assert pinned[1].startswith("MULEBOX_SIMULATOR=$(env "
                                "DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcrun")
    script = jobspec.build_script(None, ["true"], lines)
    assert script.index("simctl create") < script.index("\ntrue")
    with pytest.raises(simulator.SimulatorMissing):
        simulator.for_job({"needs": ["simulator"]}, [], "job-01ABC")


DEVICES = json.dumps({"devices": {
    "com.apple.CoreSimulator.SimRuntime.iOS-26-0": [
        {"udid": "AAA", "name": "mulebox-job-01ABC", "state": "Booted"},
        {"udid": "BBB", "name": "mulebox-job-01XYZ", "state": "Shutdown"},
        {"udid": "CCC", "name": "iPhone 17 Pro", "state": "Shutdown"},
        {"udid": "DDD", "name": "mulebox-job-01ABC copy", "state": "Shutdown"},
    ],
    "com.apple.CoreSimulator.SimRuntime.watchOS-26-0": [
        {"udid": "EEE", "name": "mulebox-job-02", "state": "Shutdown"}, "junk"],
}})


class Simctl:
    def __init__(self, fail_delete=False):
        self.calls, self.fail_delete = [], fail_delete

    def __call__(self, argv, timeout_s=None, env=None):
        self.calls.append((tuple(argv[2:]), (env or {}).get("DEVELOPER_DIR")))
        if argv[2] == "list":
            return subprocess.CompletedProcess(argv, 0, DEVICES, "")
        code = 1 if argv[2] == "delete" and self.fail_delete else 0
        return subprocess.CompletedProcess(argv, code, "", "busy" if code else "")


def test_a_jobs_simulator_is_removed_by_its_name_alone():
    simctl = Simctl()
    sims = simulator.Simulators(lambda: "/Applications/Xcode.app/Contents/Developer", simctl)
    assert sims.remove("job-01ABC") == 1
    assert [c for c, _ in simctl.calls] == [("list", "devices", "--json"),
                                            ("shutdown", "AAA"), ("delete", "AAA")]
    assert {d for _, d in simctl.calls} == {"/Applications/Xcode.app/Contents/Developer"}


def test_a_worker_that_starts_removes_every_job_simulator_and_nothing_else():
    simctl = Simctl()
    assert simulator.Simulators(lambda: XCODE_DIR, simctl).remove_leftovers() == 3
    deleted = [c[1] for c, _ in simctl.calls if c[0] == "delete"]
    assert deleted == ["AAA", "BBB", "EEE"]  # not the user's own, nor a near name


def test_with_no_xcode_nothing_is_asked():
    simctl = Simctl()
    assert simulator.Simulators(lambda: None, simctl).remove_leftovers() == 0
    assert simctl.calls == []


def test_a_failed_delete_is_tried_again():
    sims = simulator.Simulators(lambda: XCODE_DIR, Simctl(fail_delete=True))
    with pytest.raises(MuleboxError, match="busy"):
        sims.remove("job-01ABC")


@pytest.mark.parametrize("answer", ["not json", "{}", '{"devices": []}'])
def test_an_unreadable_device_list_is_tried_again_not_taken_as_removed(answer):
    def simctl(argv, timeout_s=None, env=None):
        return subprocess.CompletedProcess(argv, 0, answer, "")

    with pytest.raises(MuleboxError, match="simctl list devices"):
        simulator.Simulators(lambda: XCODE_DIR, simctl).remove("job-01ABC")


XCODE_DIR = "/Applications/Xcode.app/Contents/Developer"
