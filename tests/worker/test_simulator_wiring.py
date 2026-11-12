"""A job's simulator through the worker: offered, made in its script, removed on every
outcome and after a crash (worker/simulator.py, runspec.py, cleaner.py, advert.py)."""

import pytest

from mulebox.client import doctor
from mulebox.common.config import ProjectConfig
from mulebox.common.ids import new_id
from mulebox.worker import advert, runspec, simulator, xcode
from mulebox.worker.cleaner import Cleaner
from mulebox.worker.ports import PortPool

from .fakes import claim_body
from .test_simulator import RUNTIMES


class FakeSimulators:
    def __init__(self, fail=False):
        self.removed, self.leftovers, self.fail = [], 0, fail

    def remove(self, job_id):
        if self.fail:
            raise simulator.MuleboxError("simctl busy")
        self.removed.append(job_id)
        return 1

    def remove_leftovers(self):
        self.leftovers += 1
        return 2


@pytest.fixture
def scanned(monkeypatch, tmp_path):
    app = tmp_path / "Xcode.app"
    (app / "Contents" / "Developer").mkdir(parents=True)
    done = xcode.Scan({"xcode": ["27.2"], "simulator": ["iOS 26.0"]})
    done.xcodes = (xcode.Xcode("27.2", app),)
    done.runtimes = {"27.2": tuple(simulator.parse_runtimes(RUNTIMES))}
    monkeypatch.setattr(xcode, "_INVENTORY", xcode.Inventory(ask=lambda: done,
                                                             start=lambda work: work()))
    xcode.report()
    return app


def test_a_job_asking_for_one_makes_it_first(paths, tmp_path, scanned):
    machine = runspec.Machine("mac-1", paths, None, PortPool())
    job_id = new_id("job")
    claim = {**claim_body(["xcodebuild", "test"]), "needs": ["simulator"]}
    spec, _ = runspec.build(machine, job_id, claim, tmp_path, tmp_path / "out.log", [])
    script = spec.argv[2]
    assert f"simctl create mulebox-{job_id}" in script
    assert f"DEVELOPER_DIR={scanned}/Contents/Developer xcrun" in script  # the scanned Xcode
    assert script.index("simctl create") < script.index("xcodebuild test")
    plain, _ = runspec.build(machine, new_id("job"), claim_body(["true"]), tmp_path,
                             tmp_path / "out.log", [])
    assert "simctl" not in plain.argv[2]
    pinned = {**claim, "toolchain": {"xcode": "27.2"}}
    spec, _ = runspec.build(machine, new_id("job"), pinned, tmp_path, tmp_path / "out.log", [])
    assert "env DEVELOPER_DIR" not in spec.argv[2]  # the job's own DEVELOPER_DIR makes it
    assert spec.env["DEVELOPER_DIR"] == f"{scanned}/Contents/Developer"
    with pytest.raises(simulator.SimulatorMissing, match="iOS 9.0"):
        runspec.build(machine, new_id("job"), {**claim, "toolchain": {"simulator": "iOS 9.0"}},
                      tmp_path, tmp_path / "out.log", [])


def test_a_mac_with_a_runtime_offers_simulator(node, paths, monkeypatch):
    monkeypatch.setattr(advert, "by_name", lambda p: {"xcode": ["27.2"], "simulator": ["iOS 26"]})
    offers = advert.fields(node, paths)["capabilities"]
    assert "xcode" in offers and "simulator" in offers
    monkeypatch.setattr(advert, "by_name", lambda p: {"xcode": ["27.2"], "simulator": []})
    assert "simulator" not in advert.fields(node, paths)["capabilities"]  # no runtime
    assert "simulator" in ProjectConfig(project="app", jobs={"t": "x"},
                                        needs=("simulator",)).all_needs
    assert "simulator" in ProjectConfig(project="app", jobs={"t": "x"},
                                        toolchain={"simulator": "iOS 26.0"}).all_needs


def test_the_cleaner_removes_it_on_every_outcome_and_after_a_crash(paths):
    sims = FakeSimulators()
    cleaner = Cleaner(paths, "mac-1", None, sims)
    asked, other = new_id("job"), new_id("job")
    cleaner.clean("app", asked, uses_docker=False, uses_simulator=True)
    cleaner.clean("app", other, uses_docker=False)  # asked for none
    assert sims.removed == [asked]
    assert cleaner.recover() == ["2 job simulators"] and sims.leftovers == 1
    with pytest.raises(simulator.MuleboxError):  # the agent tries again
        Cleaner(paths, "mac-1", None, FakeSimulators(fail=True)).clean(
            "app", asked, uses_docker=False, uses_simulator=True)
    assert Cleaner(paths, "build-1", None, None).recover() == []  # Linux: nothing to ask


def test_doctor_fails_a_runtime_no_mac_has():
    project = ProjectConfig(project="app", jobs={"t": "x"}, toolchain={"simulator": "iOS 18.2"})
    mac = {"worker": "mac-1", "online": True, "capabilities": ["xcode", "simulator"],
           "toolchains": {"xcode": ["27.2"], "simulator": ["iOS 26.0"]}, "version": "1.0.0"}
    [found] = doctor.machines(project, [mac])
    assert found.level == "fail" and "simulator runtime iOS 18.2 (mac-1 has iOS 26.0)" in found.text
    ok = doctor.machines(ProjectConfig(project="app", jobs={"t": "x"},
                                       toolchain={"simulator": "iOS 26.0"}), [mac])
    assert [f.level for f in ok] == ["ok", "ok"] and "simulators iOS 26.0" in ok[1].text
