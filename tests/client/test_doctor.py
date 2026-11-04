"""`mulebox doctor`: the conclusions, then end to end with the fake coordinator."""

import json

from mulebox import cli
from mulebox.client import doctor
from mulebox.common.config import ProjectConfig
from mulebox.version import get_version

PROJECT = ProjectConfig(project="example-app", jobs={"check": "x"}, needs=("docker",),
                        toolchain={"node": "22.22.3"})
GOOD = {"worker": "build-1", "online": True, "capabilities": ["docker", "node"],
        "toolchains": {"node": ["20.18.1", "22.22.3"]}, "version": "1.0.0"}
YML = 'project: example-app\ntoolchain:\n  node: "22.22.3"\njobs:\n  check: x\n'


def worker(**changes):
    return {**GOOD, **changes}


def test_a_capable_online_machine_is_fine():
    found = doctor.machines(PROJECT, [GOOD])
    assert [f.level for f in found] == ["ok"] and "build-1" in found[0].text


def test_a_missing_toolchain_fails_and_lists_what_the_machine_has():
    found = doctor.machines(PROJECT, [worker(toolchains={"node": ["20.18.1"]})])
    assert found[0].level == "fail"
    assert "node 22.22.3 (has 20.18.1)" in found[0].text
    assert "mulebox toolchain install node 22.22.3" in found[0].text


def test_a_missing_capability_fails():
    found = doctor.machines(PROJECT, [worker(capabilities=["node"])])
    assert found[0].level == "fail" and "capability docker" in found[0].text


def test_one_able_machine_is_enough():
    found = doctor.machines(PROJECT, [worker(worker="build-2", toolchains={}), GOOD])
    assert found[0].level == "ok" and "build-1" in found[0].text


def test_only_offline_machines_is_a_warning():
    assert doctor.machines(PROJECT, [worker(online=False)])[0].level == "warn"


def test_no_machines_yet_is_a_warning():
    assert doctor.machines(PROJECT, [])[0].level == "warn"


def test_a_worker_that_does_not_report_toolchains_is_unconfirmed_not_failed():
    found = doctor.machines(PROJECT, [worker(toolchains=None)])
    assert found[0].level == "warn" and "did not report" in found[0].text


def test_a_project_with_no_toolchain_needs_no_report():
    project = ProjectConfig(project="example-app", jobs={"check": "x"})
    assert doctor.machines(project, [worker(toolchains=None)])[0].level == "ok"


def test_versions_warn_on_a_difference_only():
    same = doctor.versions("1.0.0", {"version": "1.0.0", "workers": [GOOD]})
    assert [f.level for f in same] == ["ok"]
    other = doctor.versions("1.1.0", {"version": "1.0.0", "workers": []})
    assert other[0].level == "warn" and "client 1.1.0, build machine 1.0.0" in other[0].text


def test_versions_warn_about_a_worker_behind_its_coordinator():
    found = doctor.versions("1.0.0", {"version": "1.0.0", "workers": [worker(version="0.9.0")]})
    assert [f.level for f in found] == ["ok", "warn"]


def run(capsys, *argv):
    code = cli.main(["doctor", *argv])
    return code, capsys.readouterr()


def in_project(make_repo, monkeypatch):
    monkeypatch.chdir(make_repo(tracked={".mulebox.yml": YML}))


def test_cli_all_good(fake, make_repo, monkeypatch, capsys):
    in_project(make_repo, monkeypatch)
    fake.scenario(machine_version=get_version(), workers=[worker(version=get_version())])
    code, out = run(capsys)
    assert code == 0 and "ok    config" in out.out and "ok    machine" in out.out
    assert [r["type"] for r in fake.requests()] == ["machines"]  # no job, no upload


def test_cli_missing_toolchain_exits_1_with_alternatives(fake, make_repo, monkeypatch, capsys):
    in_project(make_repo, monkeypatch)
    fake.scenario(machine_version=get_version(), workers=[worker(toolchains={"node": ["20.18.1"]})])
    code, out = run(capsys)
    assert code == 1 and "has 20.18.1" in out.out


def test_cli_json_has_stable_keys(fake, make_repo, monkeypatch, capsys):
    in_project(make_repo, monkeypatch)
    fake.scenario(machine_version="0.0.1", workers=[worker(version="0.0.1")])
    code, out = run(capsys, "--json")
    data = json.loads(out.out)
    assert code == 0 and data["result"] == "warn"
    assert {"level", "topic", "text"} == set(data["findings"][0])


def test_cli_broken_config_exits_2_and_still_reports_the_machine(fake, make_repo, monkeypatch,
                                                                 capsys):
    monkeypatch.chdir(make_repo(tracked={".mulebox.yml": "project: [\n"}))
    fake.scenario(machine_version=get_version(), workers=[GOOD])
    code, out = run(capsys)
    assert code == 2 and "fail  config" in out.out and "ok    machine" in out.out


def test_cli_outside_a_project_exits_2(fake, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake.scenario(machine_version=get_version(), workers=[GOOD])
    code, out = run(capsys)
    assert code == 2 and ".mulebox.yml" in out.out


def test_cli_unreachable_exits_3(fake, make_repo, monkeypatch, capsys):
    in_project(make_repo, monkeypatch)
    fake.scenario(down=True)
    code, out = run(capsys)
    assert code == 3 and "ok    config" in out.out and "unreachable" in out.out


def test_cli_a_coordinator_too_old_to_answer_still_gives_its_version(fake, make_repo, monkeypatch,
                                                                     capsys):
    in_project(make_repo, monkeypatch)
    fake.scenario(unknown_requests=["machines"], machine_version="0.1.0")
    code, out = run(capsys)
    assert code == 0 and "build machine 0.1.0" in out.out and "too old" in out.out


def test_cli_another_coordinator_error_is_not_mistaken_for_an_old_one(fake, make_repo, monkeypatch,
                                                                      capsys):
    in_project(make_repo, monkeypatch)
    fake.scenario(error="internal")
    code, out = run(capsys)
    assert code == 4 and "scripted failure" in out.err
