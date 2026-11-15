"""Proof that tests ran, end to end: the real client and coordinator, a stand-in worker."""

from client.test_detached import FakeWorker

from mulebox import cli
from mulebox.client import report


def sent(local, capsys, log, *flags):
    assert cli.main(["check", "test", "--again", "--detach", *flags]) == 0
    job_id = capsys.readouterr().out.strip()
    FakeWorker(local.store, local.staging, log=(log,), exit_code=0).run_next()
    code = cli.main(["wait", job_id])
    return code, capsys.readouterr().err


def test_fewer_tests_fail_and_a_reason_lets_them_pass(local, in_project, capsys):
    assert sent(local, capsys, "==== 40 passed in 1.00s ====\n")[0] == 0
    code, err = sent(local, capsys, "==== 38 passed in 1.00s ====\n")
    assert code == report.EXIT_TESTS and "the last pass on main ran 40 tests" in err
    code, err = sent(local, capsys, "==== 38 passed in 1.00s ====\n",
                     "--fewer-tests", "removed the old importer")
    assert code == 0 and "(40 tests): removed the old importer" in err


def test_a_pass_with_no_tests_is_exit_8(local, in_project, capsys):
    code, err = sent(local, capsys, "==== no tests ran in 0.01s ====\n")
    assert code == report.EXIT_TESTS and "ran none" in err


def test_a_bad_tests_setting_is_a_usage_error(local, make_repo, monkeypatch, capsys):
    from client.conftest import PROJECT_YML
    monkeypatch.chdir(make_repo(tracked={".mulebox.yml": PROJECT_YML + "tests: maybe\n"}))
    assert cli.main(["check", "test"]) == report.EXIT_USAGE
    assert "must be true, false or required" in capsys.readouterr().err


def test_a_job_of_its_own_can_turn_it_off(local, make_repo, monkeypatch, capsys):
    from client.conftest import PROJECT_YML
    yml = PROJECT_YML.replace("  test: ", "  test:\n    tests: false\n    run: ", 1)
    monkeypatch.chdir(make_repo(tracked={".mulebox.yml": yml}))
    assert sent(local, capsys, "==== no tests ran in 0.01s ====\n")[0] == 0
