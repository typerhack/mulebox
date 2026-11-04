"""Detached jobs end to end: the real client and the real coordinator code, on this machine.

`local` (conftest.py) replaces ssh with a local process; `FakeWorker` drives a job through the
worker's messages. The lease sweep is called with a clock far ahead, as if the client had
been gone for hours.
"""

import re
import threading
import time

from coordinator.helpers import queued, request, submit_body

from mulebox import cli
from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import api, leases, store as st

JOB_RE = r"job-[0-9A-Z]{26}"
HOURS_LATER = 6 * 3600.0


def message(kind, **body):
    return Message(kind, "req-test", body)


class FakeWorker:
    """What `worker/agent.py` tells the coordinator about one job."""

    def __init__(self, store, staging, log=("line one\n", "boom\n"), exit_code=3, pause=0.0):
        self.store, self.staging = store, staging
        self.log, self.exit_code, self.pause = log, exit_code, pause

    def send(self, kind, **body):
        return api.handle(self.store, self.staging, message(kind, **body), time.time(),
                          cluster_slots=4)

    def claim(self):
        reply = self.send(MessageType.CLAIM, worker="build-1", capabilities=[], free_slots=1)
        return reply.body if reply.type is MessageType.CLAIM_OK else None

    def run(self, claim):
        job = {"job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}
        time.sleep(self.pause)
        self.send(MessageType.JOB_UPDATE, state="running", **job)
        time.sleep(self.pause)
        offset = 0
        for text in self.log:
            self.send(MessageType.LOG_CHUNK, offset=offset, data=text, **job)
            offset += len(text.encode())
        self.send(MessageType.JOB_UPDATE, state="cleaning", **job)
        time.sleep(self.pause)
        outcome = "passed" if self.exit_code == 0 else "failed"
        self.send(MessageType.RESULT, outcome=outcome, exit_code=self.exit_code, duration_s=1.5,
                  **job)

    def run_next(self, timeout=20.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            claim = self.claim()
            if claim:
                self.run(claim)
                return claim["job_id"]
            time.sleep(0.05)
        raise AssertionError("no job came up")


def detach(capsys):
    assert cli.main(["check", "test", "--detach"]) == 0
    captured = capsys.readouterr()
    return captured.out.strip(), captured


def stderr_shape(text, job_id):
    """stderr of a run with the job id and the timings taken out."""
    lines = [line.replace(job_id, "<job>") for line in text.splitlines()]
    return [re.sub(r" in \d+s$", "", line) for line in lines
            if "submitted" not in line and "snapshot" not in line]


def test_detach_prints_only_the_job_id_and_returns(local, in_project, capsys):
    job_id, captured = detach(capsys)
    assert re.fullmatch(JOB_RE, job_id) and captured.out == job_id + "\n"
    assert f"mulebox wait {job_id}" in captured.err
    assert f"mulebox events --job {job_id}" in captured.err
    job = local.store.get_job(job_id)
    assert job["state"] == "queued" and job["detached"] is True


def test_a_queued_detached_job_survives_lease_expiry(local, in_project, capsys):
    job_id, _ = detach(capsys)
    assert leases.expire(local.store, time.time() + HOURS_LATER, local.staging) == []
    job = local.store.get_job(job_id)
    assert job["state"] == "queued" and not job["cancel_requested"]


def test_a_running_detached_job_survives_lease_expiry_and_keeps_its_result(local, in_project,
                                                                           capsys):
    job_id, _ = detach(capsys)
    worker = FakeWorker(local.store, local.staging)
    claim = worker.claim()
    assert claim["job_id"] == job_id
    later = time.time() + leases.CLIENT_LEASE_S + 5  # the worker stays in touch, the client not
    leases.renew_worker(local.store, job_id, claim["attempt_id"], later)
    assert leases.expire(local.store, later, local.staging) == []
    assert not local.store.get_job(job_id)["cancel_requested"]
    worker.run(claim)
    assert cli.main(["wait", job_id]) == 3
    assert "line one\nboom\n" == capsys.readouterr().out


def test_a_detached_job_is_still_interrupted_when_its_worker_dies(local, in_project, capsys):
    job_id, _ = detach(capsys)
    FakeWorker(local.store, local.staging).claim()
    leases.expire(local.store, time.time() + leases.WORKER_LEASE_S + 5, local.staging)
    job = local.store.get_job(job_id)
    assert job["state"] == "finished" and job["outcome"] == "interrupted"
    assert cli.main(["wait", job_id]) == 75


def test_a_detached_job_can_be_cancelled(local, in_project, capsys):
    job_id, _ = detach(capsys)
    assert cli.main(["cancel", job_id]) == 0
    assert cli.main(["wait", job_id]) == 130


def test_wait_returns_what_an_attached_check_returns(local, in_project, capsys):
    worker = FakeWorker(local.store, local.staging)
    thread = threading.Thread(target=worker.run_next)
    thread.start()
    attached_code = cli.main(["check", "test"])
    thread.join()
    attached = capsys.readouterr()
    attached_id = re.search(JOB_RE, attached.err)[0]

    job_id, _ = detach(capsys)
    worker.run_next()
    waited_code = cli.main(["wait", job_id])
    waited = capsys.readouterr()

    assert attached_code == waited_code == 3
    assert attached.out == waited.out == "line one\nboom\n"
    assert stderr_shape(attached.err, attached_id) == stderr_shape(waited.err, job_id)
    assert "failure summary" in waited.err


def test_wait_warns_when_files_changed_since_the_snapshot(local, in_project, capsys):
    job_id, _ = detach(capsys)
    FakeWorker(local.store, local.staging, exit_code=0).run_next()
    (in_project / "new.txt").write_text("changed\n")
    assert cli.main(["wait", job_id]) == 0
    assert "stale" in capsys.readouterr().err


def test_wait_from_elsewhere_has_no_stale_check(local, in_project, capsys, tmp_path, monkeypatch):
    job_id, _ = detach(capsys)
    FakeWorker(local.store, local.staging, exit_code=0).run_next()
    (in_project / "new.txt").write_text("changed\n")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["wait", job_id]) == 0
    assert "stale" not in capsys.readouterr().err


def test_an_interrupted_wait_leaves_the_job_alone(local, in_project, capsys, monkeypatch):
    from mulebox.client import job_commands

    job_id, _ = detach(capsys)

    def stopped(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(job_commands.Watcher, "attach", stopped)
    assert cli.main(["wait", job_id]) == 130
    assert "keeps running" in capsys.readouterr().err
    assert local.store.get_job(job_id)["state"] == "queued"


def test_wait_for_an_unknown_job_exits_4(local, capsys):
    assert cli.main(["wait", "job-01JC3X0000000000000000ABCD"]) == 4
    assert "no job" in capsys.readouterr().err


def test_wait_with_the_machine_down_exits_3_quickly(local, capsys):
    local.drop_connection(times=1)
    started = time.monotonic()
    assert cli.main(["wait", "job-01JC3X0000000000000000ABCD"]) == 3
    assert time.monotonic() - started < 15
    err = capsys.readouterr().err
    assert "not affected" in err and "was not run" not in err


def test_run_can_detach_too(local, in_project, capsys):
    assert cli.main(["run", "--detach", "--", "true"]) == 0
    job_id = capsys.readouterr().out.strip()
    job = local.store.get_job(job_id)
    assert job["detached"] is True and job["argv"] == ["true"]


def test_an_attached_job_still_gets_cancelled(local):
    job_id = queued(local.store, local.staging, now=time.time())
    leases.expire(local.store, time.time() + HOURS_LATER, local.staging)
    job = local.store.get_job(job_id)
    assert job["state"] == "finished" and job["outcome"] == "cancelled"


def test_the_flag_is_stored_and_echoed(local):
    reply = api.handle(local.store, local.staging,
                       request("submit", **submit_body(detached=True)), time.time())
    assert reply.body["detached"] is True
    with local.store.read() as conn:
        assert st.require_job(conn, reply.body["job_id"])["detached"] is True
    reply = api.handle(local.store, local.staging, request("submit", **submit_body()), time.time())
    assert reply.body["detached"] is False
