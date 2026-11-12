"""DarwinExecutor: a lower priority, records of its process groups, and orphans of a worker that
ran before. Real processes; nothing here needs macOS, so it runs on Linux too."""

import json
import time

from mulebox.common.safepath import Roots
from mulebox.worker.darwin_exec import RECORDS, DarwinExecutor, process_start, stop_group
from mulebox.worker.executor import RunSpec, group_alive, unit_name


def roots(tmp_path):
    for key in ("jobs", "staging"):
        (tmp_path / key).mkdir(exist_ok=True)
    return Roots.from_config({"jobs": str(tmp_path / "jobs"),
                              "staging": str(tmp_path / "staging")})


def executor(tmp_path, **kw):
    return DarwinExecutor(grace_s=2.0, records=tmp_path / "staging" / RECORDS,
                          roots=roots(tmp_path), **kw)


def spec(tmp_path, script, job="job-a"):
    return RunSpec(name=unit_name(job), argv=("sh", "-c", script), cwd=tmp_path, env={},
                   log_path=tmp_path / f"{job}.log", timeout_s=30.0)


def wait(ex, handle, limit=20.0):
    end = time.monotonic() + limit
    while time.monotonic() < end:
        code = ex.poll(handle)
        if code is not None:
            return code
        time.sleep(0.05)
    raise AssertionError("the job did not end")


def started(ex, handle, log, limit=10.0):
    end = time.monotonic() + limit
    while not (log.exists() and log.read_text().strip()):
        assert time.monotonic() < end, "the job printed nothing"
        time.sleep(0.02)


def test_a_job_runs_niced_and_its_record_goes_with_it(tmp_path):
    ex = executor(tmp_path)
    handle = ex.start(spec(tmp_path, "ps -o nice= -p $$"))
    record = tmp_path / "staging" / RECORDS / unit_name("job-a")
    assert json.loads(record.read_text())["pgid"] == handle.pgid
    assert wait(ex, handle) == 0
    assert (tmp_path / "job-a.log").read_text().strip() == "5"
    assert not record.exists()


def test_a_group_left_by_an_earlier_worker_is_found_and_stopped(tmp_path):
    first = executor(tmp_path)
    handle = first.start(spec(tmp_path, "echo up; sleep 60 & sleep 60"))
    started(first, handle, tmp_path / "job-a.log")
    pgid = handle.pgid
    later = executor(tmp_path)  # the worker restarted: nothing of the first one in memory
    assert later.list_orphans() == [unit_name("job-a")]
    later.kill(unit_name("job-a"))
    handle.proc.wait(timeout=5)  # reap the leader the test itself started
    assert not group_alive(pgid)
    assert not (tmp_path / "staging" / RECORDS / unit_name("job-a")).exists()
    assert later.list_orphans() == []


def test_a_record_of_a_group_that_ended_is_only_removed(tmp_path):
    ex = executor(tmp_path)
    handle = ex.start(spec(tmp_path, "exit 0", job="job-old"))
    pgid = handle.pgid
    handle.proc.wait(timeout=5)
    folder = tmp_path / "staging" / RECORDS
    assert (folder / unit_name("job-old")).exists()  # ended, but nobody polled it
    later = executor(tmp_path)
    assert not group_alive(pgid) and later.list_orphans() == []
    assert not (folder / unit_name("job-old")).exists()


def test_a_group_id_now_held_by_another_process_is_left_alone(tmp_path):
    (tmp_path / "other").mkdir()
    other = executor(tmp_path / "other")
    handle = other.start(spec(tmp_path, "echo up; sleep 60", job="job-b"))
    started(other, handle, tmp_path / "job-b.log")
    ex = executor(tmp_path)
    folder = tmp_path / "staging" / RECORDS
    folder.mkdir(parents=True, exist_ok=True)
    (folder / unit_name("job-old")).write_text(json.dumps(
        {"pgid": handle.pgid, "started": "Mon Jan  1 00:00:00 2001"}))
    assert ex.list_orphans() == []  # its first process started at another time
    ex.kill(unit_name("job-old"))
    assert group_alive(handle.pgid)  # not ours, not touched
    other.stop(handle)
    assert not group_alive(handle.pgid)


def test_process_start_and_stop_group(tmp_path):
    ex = executor(tmp_path)
    handle = ex.start(spec(tmp_path, "echo up; trap '' TERM; sleep 60"))
    started(ex, handle, tmp_path / "job-a.log")
    assert process_start(handle.pgid)
    stop_group(handle.pgid, 0.5)  # TERM is ignored, so KILL ends it
    handle.proc.wait(timeout=5)
    assert not group_alive(handle.pgid)
    assert process_start(handle.pgid) is None


def test_without_records_it_is_the_plain_process_group_executor(tmp_path):
    ex = DarwinExecutor(grace_s=1.0)
    handle = ex.start(spec(tmp_path, "exit 3"))
    assert wait(ex, handle) == 3 and ex.list_orphans() == []
