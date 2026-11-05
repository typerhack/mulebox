import io
import subprocess
from dataclasses import replace

import pytest

from mulebox.client import submit
from mulebox.client.submit import Streams, run_job
from mulebox.common.config import ProjectConfig
from mulebox.common.config_jobs import NO_SETUP, JobOptions
from mulebox.common.protocol import Message, MessageType
from mulebox.common.status import CONTAINER_LOGS_NOTE
from mulebox.common.ssh import SSHUnavailable
from mulebox.worker.jobspec import build_argv

JOB = "job-01JC3X0000000000000000ABCD"
PROJECT = ProjectConfig(
    project="example-app",
    jobs={"check": "pnpm check", "test": "pnpm test"},
    needs=("node",),
    toolchain={"node": "22.22.3"},
    setup="pnpm install --frozen-lockfile",
    timeout_min=20,
    exclude=("reports/",),
)


def msg(kind, **body):
    return Message(MessageType(kind), "req-x", body)


def log(offset, data):
    return msg("log_chunk", job_id=JOB, offset=offset, data=data)


def result(outcome="passed", code=0):
    return msg("result", job_id=JOB, outcome=outcome, exit_code=code, duration_s=65)


class FakeRemote:
    def __init__(self, streams, submit_state="uploading", status_states=("finished",)):
        self.streams = list(streams)  # one list of messages (or exceptions) per watch
        self.submit_state = submit_state
        self.status_states = list(status_states)
        self.calls, self.uploads, self.watches = [], [], []

    def call(self, m):
        self.calls.append(m)
        if m.type is MessageType.SUBMIT:
            return msg("submit_ok", job_id=JOB, state=self.submit_state)
        state = self.status_states.pop(0) if self.status_states else "finished"
        return msg("status_ok", job_id=JOB, state=state, outcome="cancelled", exit_code=None)

    def upload(self, job_id, path, sha256):
        self.uploads.append((job_id, path.exists(), sha256))
        return msg("status_ok", job_id=job_id, state="queued")

    def watch(self, job_id, offset=0, lease=True):
        self.watches.append((job_id, offset, lease))
        for item in self.streams.pop(0):
            if isinstance(item, BaseException):
                raise item
            yield item


def streams():
    return Streams(out=io.StringIO(), err=io.StringIO(), sleep=lambda s: None)


def test_passed_job_prints_log_on_stdout_and_status_on_stderr(make_repo):
    repo = make_repo()
    remote = FakeRemote([[
        msg("status_ok", job_id=JOB, state="queued", position=2),
        msg("status_ok", job_id=JOB, state="running", worker="build-1"),
        log(0, "hello\n"),
        log(6, "world\n"),
        result(),
    ]])
    io_ = streams()
    assert run_job(PROJECT, "check", repo, remote, io_) == 0
    assert io_.out.getvalue() == "hello\nworld\n"
    err = io_.err.getvalue().splitlines()
    assert all(line.startswith("mulebox: ") for line in err)
    assert f"mulebox: job {JOB} (example-app check) submitted" in err
    assert "mulebox: queued, position 2" in err
    assert "mulebox: running on build-1" in err
    assert f"mulebox: job {JOB} passed in 1m 05s" in err
    assert not any("stale" in line for line in err)
    assert remote.uploads[0][0] == JOB and remote.uploads[0][1]
    assert remote.watches == [(JOB, 0, True)]


def test_submit_body_of_a_compose_project(make_repo):
    project = replace(PROJECT, compose=("docker-compose.yml", "docker-compose.ci.yml"),
                      env={"CI": "1"})
    remote = FakeRemote([[result()]])
    run_job(project, "test", make_repo(), remote, streams())
    body = remote.calls[0].body
    assert body["needs"] == ["node", "docker", "compose-v1"]
    assert body["env"] == {
        "CI": "1", "MULEBOX_COMPOSE_FILES": "docker-compose.yml:docker-compose.ci.yml"}


def test_a_job_without_containers_sends_no_compose_and_says_what_it_left_out(make_repo):
    project = replace(PROJECT, compose=("docker-compose.yml",), setup="pnpm install",
                      env={"URL": "http://127.0.0.1:${MULEBOX_PORT_API_8000}", "CI": "1"},
                      job_options={"test": JobOptions(setup=NO_SETUP, compose=False)})
    remote = FakeRemote([[result()]])
    io = streams()
    run_job(project, "test", make_repo(), remote, io)
    body = remote.calls[0].body
    assert body["env"] == {"CI": "1"} and body["env_order"] == ["CI"]
    assert body["setup"] is None and "docker" not in body["needs"]
    assert "URL" in io.err.getvalue()


def test_a_job_with_a_port_sends_its_name_and_others_lose_what_needs_it(make_repo):
    project = replace(PROJECT, env={"URL": "http://127.0.0.1:${MULEBOX_PORT_VITE}", "CI": "1"},
                      job_options={"test": JobOptions(ports=("vite",))})
    remote = FakeRemote([[result()], [result()]])
    repo = make_repo()
    run_job(project, "test", repo, remote, streams())
    run_job(project, "check", repo, remote, streams())
    first, other = (call.body for call in remote.calls if call.type is MessageType.SUBMIT)
    assert first["env"]["MULEBOX_HOST_PORTS"] == "vite" and "URL" in first["env"]
    assert first["env_order"] == ["URL", "CI"]
    assert other["env"] == {"CI": "1"}


def test_mulebox_run_keeps_the_top_level_values(make_repo):
    project = replace(PROJECT, setup="pnpm install",
                      job_options={"run": JobOptions(setup=NO_SETUP)})  # a job that is called run
    remote = FakeRemote([[result()]])
    run_job(project, ["ls"], make_repo(), remote, streams())
    assert remote.calls[0].body["setup"] == "pnpm install"


def test_a_failing_line_of_a_multi_line_job_fails_it(tmp_path):
    project = replace(PROJECT, jobs={"check": "false\necho passed anyway\n"})
    _, argv = submit.job_request(project, "check")
    done = subprocess.run(list(build_argv(None, argv)), cwd=tmp_path, capture_output=True,
                          text=True)
    assert done.returncode == 1 and "passed anyway" not in done.stdout


def test_submit_body_for_a_named_job(make_repo):
    remote = FakeRemote([[result()]])
    run_job(PROJECT, "test", make_repo(), remote, streams())
    body = remote.calls[0].body
    assert body["argv"] == ["bash", "-e", "-c", "pnpm test"]
    assert body["job"] == "test" and body["project"] == "example-app"
    assert body["setup"] == "pnpm install --frozen-lockfile"
    assert body["toolchain"] == {"node": "22.22.3"} and body["needs"] == ["node"]
    assert body["timeout_min"] == 20 and body["branch"] == "main"
    assert body["idempotency_key"].startswith("sub-")
    assert len(body["fingerprint"]) == 64 and len(body["base_commit"]) == 40


def test_run_sends_argv_as_is(make_repo):
    remote = FakeRemote([[result()]])
    run_job(PROJECT, ["pnpm", "exec", "vitest", "run", "a b.test.ts"], make_repo(), remote,
            streams())
    body = remote.calls[0].body
    assert body["argv"] == ["pnpm", "exec", "vitest", "run", "a b.test.ts"]
    assert body["job"] == "run"


@pytest.mark.parametrize(
    "outcome, code, expected",
    [("passed", 0, 0), ("failed", 2, 2), ("failed", None, 5), ("failed", 0, 1),
     ("timed_out", None, 124), ("cancelled", None, 130), ("interrupted", None, 75)],
)
def test_exit_codes(make_repo, outcome, code, expected):
    remote = FakeRemote([[result(outcome, code)]])
    assert run_job(PROJECT, "check", make_repo(), remote, streams()) == expected


def test_repeat_submit_skips_the_upload(make_repo):
    remote = FakeRemote([[result()]], submit_state="queued")
    run_job(PROJECT, "check", make_repo(), remote, streams())
    assert remote.uploads == []


def test_snapshot_file_is_removed(make_repo):
    remote = FakeRemote([[result()]])
    seen = []
    real = remote.upload
    remote.upload = lambda j, p, s: (seen.append(p), real(j, p, s))[1]
    run_job(PROJECT, "check", make_repo(), remote, streams())
    assert seen and not seen[0].exists()


def test_stale_warning_when_files_change_during_the_job(make_repo):
    repo = make_repo(tracked={"a.txt": "one"})

    def change():
        (repo / "a.txt").write_text("two")
        yield result()

    remote = FakeRemote([change()])
    io_ = streams()
    assert run_job(PROJECT, "check", repo, remote, io_) == 0
    assert "stale" in io_.err.getvalue()


def test_ctrl_c_cancels_and_returns_130(make_repo):
    remote = FakeRemote([[log(0, "partial\n"), KeyboardInterrupt()]],
                        status_states=["running", "running", "finished"])
    io_ = streams()
    assert run_job(PROJECT, "check", make_repo(), remote, io_) == 130
    kinds = [c.type for c in remote.calls]
    assert kinds == [MessageType.SUBMIT, MessageType.CANCEL, MessageType.STATUS,
                     MessageType.STATUS]
    err = io_.err.getvalue()
    assert f"cancelling job {JOB}" in err and "cancelled" in err


def test_ctrl_c_gives_up_waiting_after_the_deadline(make_repo, monkeypatch):
    monkeypatch.setattr(submit, "CANCEL_WAIT_S", 0.0)
    remote = FakeRemote([[KeyboardInterrupt()]], status_states=["running"] * 5)
    io_ = streams()
    assert run_job(PROJECT, "check", make_repo(), remote, io_) == 130
    assert "did not confirm" in io_.err.getvalue()


def test_reconnects_from_the_last_offset(make_repo):
    remote = FakeRemote([
        [log(0, "one\n"), SSHUnavailable("dropped")],
        [log(0, "one\n"), log(4, "two\n"), result()],  # a replay overlaps
    ])
    io_ = streams()
    assert run_job(PROJECT, "check", make_repo(), remote, io_) == 0
    assert io_.out.getvalue() == "one\ntwo\n"
    assert remote.watches == [(JOB, 0, True), (JOB, 4, True)]
    assert "reconnecting" in io_.err.getvalue()


def test_gives_up_after_repeated_connection_loss(make_repo):
    remote = FakeRemote([[SSHUnavailable("down")]] * (submit.WATCH_RETRIES + 1))
    io_ = streams()
    with pytest.raises(submit.WatchLost, match=f"mulebox wait {JOB}") as info:
        run_job(PROJECT, "check", make_repo(), remote, io_)
    assert "may still be running" in str(info.value)  # never "was not run": it was submitted


def test_partial_overlap_is_trimmed():
    watcher = submit.Watcher(None, streams())
    watcher.handle(log(0, "abc"))
    watcher.handle(log(1, "bcdef"))
    assert watcher.io.out.getvalue() == "abcdef" and watcher.offset == 6


def test_submit_body_keeps_the_env_order_of_the_file(make_repo):
    remote = FakeRemote([[result()]])
    project = replace(PROJECT, env={"Z_HOST": "db", "A_URL": "${Z_HOST}"})
    run_job(project, "check", make_repo(), remote, streams())
    assert remote.calls[0].body["env_order"] == ["Z_HOST", "A_URL"]


def test_the_failure_summary_is_the_last_thing_printed_after_the_container_logs(
        make_repo, monkeypatch):
    monkeypatch.setattr(submit, "current_fingerprint", lambda *_: "changed")
    text = (f"src/a.ts(1,1): error TS2322: the real error\n{CONTAINER_LOGS_NOTE}\n"
            + "db  | a line of a container\n" * 3)
    remote = FakeRemote([[log(0, text), result("failed", 2)]])
    io_ = streams()
    assert run_job(PROJECT, "check", make_repo(), remote, io_) == 2
    assert io_.out.getvalue().endswith("db  | a line of a container\n")
    err = io_.err.getvalue().splitlines()
    assert any("stale" in line for line in err)
    assert err[-1].endswith("the real error")
    assert not any("a line of a container" in line for line in err)


def test_the_left_out_notice_reads_for_one_entry_and_for_more():
    assert submit.left_out(["A"]) == ("this job leaves out the env: entry A, which uses a port "
                                      "it does not have")
    assert "entries A, B, which use a port" in submit.left_out(["A", "B"])
