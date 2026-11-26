"""A failed compose job kept, and rerun from a stage (agent_kept.py, rerun.py). Setup:
test_agent_compose.py; the job scripts really run, with a stand-in `docker` on PATH."""

from mulebox.common import compose
from mulebox.common.protocol import MessageType

from .fake_docker import ok
from .fakes import claim_body
from .test_agent_compose import (  # noqa: F401
    FOREIGN,
    add_resources,
    agent,
    clock,
    daemon,
    run_until,
    stand_in,
    submit,
)

ENV = {compose.COMPOSE_FILES_KEY: "docker-compose.yml", "APP_ENV": "ci"}


def results(link, count):
    return lambda: len(link.of_type(MessageType.RESULT)) >= count


def running(daemon, home):
    """`docker ps` says the kept job's containers are up (kept.stopped)."""
    daemon.responses[("ps", "-a", "--filter", compose.project_filter(home), "--format")] = ok(
        "api\tUp 2 minutes\n")


def rerun(link, command, first, stage="command", setup="echo setup ran"):
    body = {**claim_body(["bash", "-c", command], setup=setup), "env": dict(ENV),
            "reuses": first, "from_stage": stage}
    link.claims.append(body)
    return body["job_id"]


def calls_after(stand_in, count):
    return [line.split(" | ") for line in stand_in.read_text().splitlines()[count:]]


def fail_first(agent, fake_link, daemon, stand_in):
    first = submit(fake_link, "exit 7", setup="echo setup ran")
    add_resources(daemon, first)
    run_until(agent, results(fake_link, 1))
    assert first in agent.kept.jobs
    return first, len(stand_in.read_text().splitlines())


def test_a_rerun_from_command_runs_in_the_kept_containers(agent, fake_link, daemon, paths,
                                                          stand_in):
    first, before = fail_first(agent, fake_link, daemon, stand_in)
    running(daemon, first)
    second = rerun(fake_link, "docker compose exec -T api true; echo fixed", first)
    run_until(agent, results(fake_link, 2))
    result = fake_link.of_type(MessageType.RESULT)[1].body
    assert (result["job_id"], result["outcome"]) == (second, "passed")
    calls = calls_after(stand_in, before)
    assert [c[0] for c in calls] == ["compose exec -T api true"]  # no `up`, no setup
    assert calls[0][1] == compose.project_name(first)  # the kept job's compose project
    assert calls[0][2] == str(paths.job_dir("example-app", first) / "compose.mulebox.yml")
    text = fake_link.log_text()
    assert f"rerun from command with the containers of {first} (images, services, setup skipped)" in text
    assert text.count("setup ran") == 1  # the first job's only
    # passed, so nothing is kept: the first job's containers and both folders are gone
    assert sorted(daemon.left()) == sorted(FOREIGN)
    assert not paths.job_dir("example-app", first).exists()
    assert not paths.job_dir("example-app", second).exists()
    assert not agent.ports._held and not agent.kept.jobs


def test_a_rerun_from_setup_runs_setup_again(agent, fake_link, daemon, stand_in):
    first, _ = fail_first(agent, fake_link, daemon, stand_in)
    running(daemon, first)
    rerun(fake_link, "echo fixed", first, stage="setup")
    run_until(agent, results(fake_link, 2))
    assert fake_link.log_text().count("setup ran") == 2


def test_a_rerun_that_fails_again_is_kept_with_the_same_containers(agent, fake_link, daemon,
                                                                   stand_in, clock):
    first, _ = fail_first(agent, fake_link, daemon, stand_in)
    running(daemon, first)
    second = rerun(fake_link, "exit 3", first)
    run_until(agent, results(fake_link, 2))
    kept = agent.kept.jobs[second]
    assert kept.home == first and first not in agent.kept.jobs
    assert f"containers-{first}" in daemon.left()
    clock.now += 15 * 60 + 1
    run_until(agent, lambda: not agent.kept.jobs and not agent.unkeeping)
    assert sorted(daemon.left()) == sorted(FOREIGN)


def test_a_change_to_setup_runs_from_the_start(agent, fake_link, daemon, stand_in):
    first, before = fail_first(agent, fake_link, daemon, stand_in)
    running(daemon, first)
    rerun(fake_link, "echo fixed", first, setup="echo another setup")
    run_until(agent, results(fake_link, 2))
    text = fake_link.log_text()
    assert "cannot rerun from the kept job: something the skipped stages depend on changed" in text
    assert "compose up --no-start" in [c[0] for c in calls_after(stand_in, before)]
    assert f"containers-{first}" not in daemon.left()


def test_stopped_containers_run_from_the_start(agent, fake_link, daemon, stand_in):
    first, before = fail_first(agent, fake_link, daemon, stand_in)
    daemon.responses[("ps", "-a", "--filter", compose.project_filter(first), "--format")] = ok(
        "api\tExited (137) 1 minute ago\n")
    rerun(fake_link, "echo fixed", first)
    run_until(agent, results(fake_link, 2))
    assert "container api is not running (Exited (137)" in fake_link.log_text()
    assert "compose up --no-start" in [c[0] for c in calls_after(stand_in, before)]


def test_another_job_of_the_branch_removes_the_kept_one_first(agent, fake_link, daemon,
                                                              stand_in):
    first, _ = fail_first(agent, fake_link, daemon, stand_in)
    submit(fake_link, "echo clean run")
    run_until(agent, results(fake_link, 2))
    assert first not in agent.kept.jobs and f"containers-{first}" not in daemon.left()
    assert fake_link.of_type(MessageType.RESULT)[1].body["outcome"] == "passed"


def test_nothing_is_kept_with_keep_failed_min_zero(agent, fake_link, daemon, paths):
    agent.node = agent.node.__class__(**{**agent.node.__dict__, "storage": agent.node.storage
                                         .__class__(keep_failed_min=0)})
    first = submit(fake_link, "exit 7")
    add_resources(daemon, first)
    run_until(agent, results(fake_link, 1))
    assert not agent.kept.jobs and sorted(daemon.left()) == sorted(FOREIGN)
