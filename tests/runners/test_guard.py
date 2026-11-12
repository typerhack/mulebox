"""The guard a runner's job-started hook runs first: forks and other accounts refused."""

import json

import pytest

from mulebox.runners import guard

SAME = {"id": 7, "full_name": "example-org/example-app"}
FORK = {"id": 9, "full_name": "mallory/example-app"}


def env_for(tmp_path, event, **extra):
    path = tmp_path / "event.json"
    path.write_text(event if isinstance(event, str) else json.dumps(event))
    return {"GITHUB_EVENT_PATH": str(path), "GITHUB_ACTOR": "alice", **extra}


def pr(head, base=SAME):
    return {"pull_request": {"head": {"repo": head}, "base": {"repo": base}}}


def test_a_push_from_the_repository_runs(tmp_path):
    assert guard.refusal(env_for(tmp_path, {"ref": "refs/heads/main"}), {}) is None


def test_a_pull_request_from_a_branch_runs(tmp_path):
    assert guard.refusal(env_for(tmp_path, pr(SAME)), {}) is None


@pytest.mark.parametrize("head", [FORK, None, {"id": None}, {"id": "7"}, {"id": True},
                                  {"id": 0}])
def test_a_pull_request_from_a_fork_or_a_deleted_one_is_refused(tmp_path, head):
    reason = guard.refusal(env_for(tmp_path, pr(head)), {})
    assert reason and reason.startswith("a pull request from")


def test_the_fork_is_named(tmp_path):
    assert guard.refusal(env_for(tmp_path, pr(FORK)), {}) == \
        "a pull request from mallory/example-app"


def test_a_follow_on_run_of_a_fork_is_refused(tmp_path):
    event = {"workflow_run": {"head_repository": FORK, "repository": SAME}}
    assert "follow-on run of mallory/example-app" in guard.refusal(env_for(tmp_path, event), {})
    event = {"workflow_run": {"head_repository": SAME, "repository": SAME}}
    assert guard.refusal(env_for(tmp_path, event), {}) is None


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"a": 1} {"b": 2}', "null"])
def test_an_event_file_that_is_not_one_object_is_refused(tmp_path, text):
    assert guard.refusal(env_for(tmp_path, text), {}) == "a job with no readable event file"


def test_no_event_file_is_refused(tmp_path):
    assert guard.refusal({"GITHUB_ACTOR": "alice"}, {}) == "a job with no readable event file"
    env = {"GITHUB_EVENT_PATH": str(tmp_path / "missing.json"), "GITHUB_ACTOR": "alice"}
    assert guard.refusal(env, {}) == "a job with no readable event file"


def test_only_the_registered_accounts_run(tmp_path):
    meta = {"actors": ["Alice", "dependabot[bot]"]}
    assert guard.refusal(env_for(tmp_path, {}), meta) is None  # GitHub logins ignore case
    bob = env_for(tmp_path, {}, GITHUB_ACTOR="bob")
    assert guard.refusal(bob, meta) == "a run started by bob"


def test_a_re_run_by_another_account_is_refused(tmp_path):
    env = env_for(tmp_path, {}, GITHUB_TRIGGERING_ACTOR="mallory")
    assert guard.refusal(env, {"actors": ["alice"]}) == "a run started by mallory"


def test_a_run_with_no_actor_is_refused_when_accounts_are_set(tmp_path):
    env = env_for(tmp_path, {}, GITHUB_ACTOR="")
    assert guard.refusal(env, {"actors": ["alice"]}) == "a run with no actor"


def test_the_fork_rule_holds_for_a_registered_account(tmp_path):
    assert guard.refusal(env_for(tmp_path, pr(FORK)), {"actors": ["alice"]})


@pytest.mark.parametrize("actors", ["alice", [1], [""], {"alice": 1}])
def test_unreadable_accounts_refuse_every_job(tmp_path, actors):
    reason = guard.refusal(env_for(tmp_path, {}), {"actors": actors})
    assert reason == "every job: its registered accounts cannot be read"


def test_a_public_runner_with_no_accounts_refuses_every_job(tmp_path):
    reason = guard.refusal(env_for(tmp_path, {}), {"public": True, "actors": []})
    assert reason and reason.startswith("every job")


def test_a_comment_on_a_pull_request_is_refused(tmp_path):
    event = {"issue": {"number": 3, "pull_request": {"url": "https://example.invalid/pr/3"}}}
    assert guard.refusal(env_for(tmp_path, event), {"actors": ["alice"]}) == \
        "a run started by a comment on a pull request"
    assert guard.refusal(env_for(tmp_path, {"issue": {"number": 4}}), {}) is None


def test_metadata_missing_or_unreadable_refuses_every_job(tmp_path):
    assert guard.runner_meta(tmp_path) is None  # `runner add` always writes it
    assert guard.runner_meta(None) is None
    (tmp_path / ".mulebox-runner.json").write_text("[]")
    assert guard.runner_meta(tmp_path) is None
    assert "missing or cannot be read" in guard.refusal(env_for(tmp_path, {}), None)
    (tmp_path / ".mulebox-runner.json").write_text('{"actors": ["alice"]}')
    assert guard.runner_meta(tmp_path) == {"actors": ["alice"]}


def test_a_runner_from_before_accounts_gets_the_other_rules(tmp_path):
    assert guard.refusal(env_for(tmp_path, {}, GITHUB_ACTOR="bob"), {"repo": "a/b"}) is None
    assert guard.refusal(env_for(tmp_path, pr(FORK)), {"repo": "a/b"})


def test_kill_workers_kills_the_runners_worker_and_its_own_parent(tmp_path, monkeypatch):
    killed = []
    monkeypatch.setattr(guard, "worker_pids", lambda folder: [11, 12])
    monkeypatch.setattr(guard, "ancestor_workers", lambda: [12, 30])
    monkeypatch.setattr(guard.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    told = []
    monkeypatch.setattr(guard, "_tell", lambda pid, message: told.append(pid))
    assert guard.kill_workers(tmp_path, "why") == [11, 12, 30]
    assert {sig for _, sig in killed} == {guard.signal.SIGKILL} and told == [11, 12, 30]


def test_tell_writes_to_the_process_s_stderr(tmp_path):
    (tmp_path / "7" / "fd").mkdir(parents=True)
    (tmp_path / "7" / "fd" / "2").write_text("")
    guard._tell(7, "mulebox: this runner refuses x", tmp_path)
    assert (tmp_path / "7" / "fd" / "2").read_text() == "mulebox: this runner refuses x\n"
    guard._tell(8, "nowhere", tmp_path)  # no such process: no error


def test_ancestor_workers_walks_up_the_parents(tmp_path):
    def proc(pid, ppid, cmd):
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "stat").write_text(f"{pid} (x y) S {ppid} 1 1")
        (tmp_path / str(pid) / "cmdline").write_bytes(b"\0".join(cmd) + b"\0")

    proc(40, 30, [b"python3", b"-m", b"mulebox"])
    proc(30, 20, [b"/bin/sh", b"started.sh"])
    proc(20, 10, [b"/home/alice/.mulebox/runners/r/bin/Runner.Worker", b"spawnclient"])
    proc(10, 1, [b"/home/alice/.mulebox/runners/r/bin/Runner.Listener"])
    assert guard.ancestor_workers(40, tmp_path) == [20]
