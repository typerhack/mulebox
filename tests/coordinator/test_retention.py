"""Old logs and stage rows go; nothing else does."""

import threading

import pytest

from mulebox.common.config import ConfigError, load_node_config
from mulebox.common.ids import new_id
from mulebox.coordinator import daemon, retention, steps

from .helpers import claimed, queued
from .test_api import call

DAY = retention.DAY_S
NOW = 1000.0 + 100 * DAY


def finished(store, staging, at=1000.0):
    """A finished job with a log and one stage row; it finished at `at`."""
    claim = claimed(store, staging, now=at)
    ids = {"job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}
    call(store, staging, "log_chunk", offset=0, data="hello\n", now=at, **ids)
    call(store, staging, "steps", now=at, steps=[{"seq": 0, "stage": "command", "started_at": at,
                                                  "finished_at": at, "exit_code": 0}], **ids)
    call(store, staging, "result", now=at, outcome="passed", exit_code=0, duration_s=1, **ids)
    return claim["job_id"]


def sweep(store, staging, log_days=30, step_days=365, now=NOW):
    return retention.sweep(store, staging, now, log_days, step_days)


def rows_of(store, job_id):
    with store.read() as conn:
        return steps.for_job(conn, job_id)


def test_an_old_log_goes_and_its_rows_stay(store, staging):
    job_id = finished(store, staging)
    assert sweep(store, staging) == (1, 0)
    assert not staging.log_path(job_id).exists()
    assert rows_of(store, job_id)
    assert store.get_job(job_id)["outcome"] == "passed"


def test_a_recent_log_stays(store, staging):
    job_id = finished(store, staging, at=NOW - 29 * DAY)
    assert sweep(store, staging) == (0, 0)
    assert staging.log_path(job_id).exists()


def test_rows_go_after_their_own_time_and_the_job_stays(store, staging):
    job_id = finished(store, staging)
    assert sweep(store, staging, step_days=99) == (1, 1)
    assert rows_of(store, job_id) == [] and store.get_job(job_id) is not None


def test_a_running_jobs_log_stays(store, staging):
    claim = claimed(store, staging)
    call(store, staging, "log_chunk", offset=0, data="x", job_id=claim["job_id"],
         attempt_id=claim["attempt_id"])
    assert sweep(store, staging) == (0, 0)
    assert staging.log_path(claim["job_id"]).exists()


def test_a_log_of_no_known_job_stays(store, staging):
    path = staging.logs_dir / f"{new_id('job')}.log"
    path.write_text("from somewhere\n")
    assert sweep(store, staging) == (0, 0)
    assert path.exists()


def test_other_entries_in_the_folder_are_left_alone(store, staging, tmp_path):
    job_id = finished(store, staging)
    staging.log_path(job_id).unlink()
    outside = tmp_path / "keep.txt"
    outside.write_text("mine\n")
    (staging.logs_dir / f"{job_id}.log").symlink_to(outside)
    (staging.logs_dir / "notes.txt").write_text("a note\n")
    (staging.logs_dir / "folder.log").mkdir()
    assert sweep(store, staging) == (0, 0)
    assert outside.read_text() == "mine\n"
    assert (staging.logs_dir / "notes.txt").exists() and (staging.logs_dir / "folder.log").is_dir()


def test_a_folder_with_a_job_name_is_left_alone(store, staging):
    job_id = finished(store, staging)
    staging.log_path(job_id).unlink()
    staging.log_path(job_id).mkdir()
    (staging.log_path(job_id) / "inner").write_text("x")
    assert sweep(store, staging) == (0, 0)
    assert (staging.log_path(job_id) / "inner").exists()


def test_uploads_and_state_are_not_touched(store, staging):
    finished(store, staging)
    queued_id = queued(store, staging)
    sweep(store, staging)
    assert staging.upload_path(queued_id).exists() and staging.db_path.exists()


def test_a_log_that_cannot_go_does_not_stop_the_others(store, staging, monkeypatch):
    from mulebox.common.safepath import UnsafePath

    first, second = finished(store, staging), finished(store, staging)
    real = staging.remove_log

    def flaky(job_id):
        if job_id == first:
            raise UnsafePath("no")
        real(job_id)

    monkeypatch.setattr(staging, "remove_log", flaky)
    assert sweep(store, staging)[0] == 1
    assert staging.log_path(first).exists() and not staging.log_path(second).exists()


def test_the_service_sweeps_at_the_start_and_then_hourly(store, staging):
    job_id = finished(store, staging)
    stop = threading.Event()
    times = iter([NOW, NOW, NOW + 10, NOW + retention.DAY_S])

    def clock():
        try:
            return next(times)
        except StopIteration:
            stop.set()
            return NOW + 2 * DAY

    daemon.run(store, staging, stop, clock=clock, interval=0, log_days=30, step_days=365)
    assert not staging.log_path(job_id).exists()


def test_a_failed_sweep_does_not_stop_the_service(store, staging, monkeypatch):
    stop = threading.Event()

    def fail(*args):
        stop.set()
        raise OSError("disk")

    monkeypatch.setattr(retention, "sweep", fail)
    daemon.run(store, staging, stop, interval=0)


# Config


def node_toml(tmp_path, extra=""):
    lines = ['name = "build-1"', 'roles = ["coordinator", "worker"]', "[roots]"]
    lines += [f'{key} = "/srv/{key}"' for key in ("jobs", "cache", "staging", "runners")]
    path = tmp_path / "node.toml"
    path.write_text("\n".join(lines) + "\n" + extra)
    return path


def test_defaults(tmp_path):
    assert load_node_config(node_toml(tmp_path)).retention == {"log_days": 30, "step_days": 365}


def test_days_can_be_set(tmp_path):
    node = load_node_config(node_toml(tmp_path, "[retention]\nlog_days = 7\nstep_days = 14\n"))
    assert node.retention == {"log_days": 7, "step_days": 14}


@pytest.mark.parametrize("text", ["log_days = 0", "step_days = 10\nlog_days = 20",
                                  "days = 3", 'log_days = "7"'])
def test_bad_days_are_refused(tmp_path, text):
    with pytest.raises(ConfigError):
        load_node_config(node_toml(tmp_path, f"[retention]\n{text}\n"))
