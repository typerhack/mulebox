"""Pause and boost of a GitHub run on its runner's service (runners/runner_controls.py)."""

from mulebox.runners.runner_controls import SERVICE_WEIGHT, RunnerControls, RunnerUnit
from mulebox.worker.controls import BOOST_SHARES, BOOST_WEIGHT, NORMAL_SHARES
from mulebox.worker.docker import DockerError

UNIT = "mulebox-runner@build-1-example-app.service"


class Calls:
    """systemctl and docker stand-ins that write down what was asked, in order."""

    def __init__(self, ids=("c1",)):
        self.log, self.ids = [], list(ids)

    def systemctl(self, *args):
        self.log.append(("systemctl", *args))

    def run(self, *args):
        if args[0] == "unpause":
            raise DockerError("not paused")  # as Docker says for a running container
        self.log.append(("docker", *args))
        return ""


def job(state="running", runner="build-1-example-app", **controls):
    return {"job_id": "job-1", "state": state, "runner": runner, **controls}


def steer(calls):
    return RunnerControls(RunnerUnit(calls.systemctl), calls, lambda runner: calls.ids)


def follow(controls, jobs):
    controls.follow(jobs)
    for held, _ in controls.held.values():
        assert held.task is None or held.task.wait(5.0)
        assert held.task is None or held.task.error is None, held.task.error


def weight(value):
    return ("systemctl", "set-property", "--runtime", UNIT, f"CPUWeight={value}",
            f"IOWeight={value}")


def test_first_round_sets_the_service_as_asked():
    calls = Calls()
    follow(steer(calls), [job()])  # after a restart a freeze or boost may be left over
    assert calls.log == [weight(SERVICE_WEIGHT), ("docker", "update", "--cpu-shares",
                                                  str(NORMAL_SHARES), "c1"),
                         ("systemctl", "thaw", UNIT)]


def test_pause_freezes_the_service_and_its_containers_then_resume_thaws():
    calls, controls = Calls(), None
    controls = steer(calls)
    follow(controls, [job()])
    calls.log.clear()
    follow(controls, [job(paused=1)])
    assert calls.log == [("systemctl", "freeze", UNIT), ("docker", "pause", "c1")]
    calls.log.clear()
    follow(controls, [job()])
    assert calls.log == [("systemctl", "thaw", UNIT)]  # unpause tried first; it was not paused


def test_boost_raises_the_service_and_its_containers():
    calls, controls = Calls(), None
    controls = steer(calls)
    follow(controls, [job()])
    calls.log.clear()
    follow(controls, [job(boost=1)])
    assert calls.log == [weight(BOOST_WEIGHT),
                         ("docker", "update", "--cpu-shares", str(BOOST_SHARES), "c1")]


def test_a_run_that_ends_paused_and_boosted_is_set_back():
    calls = Calls()
    controls = steer(calls)
    follow(controls, [job(paused=1, boost=1)])
    calls.log.clear()
    follow(controls, [])
    assert calls.log == [weight(SERVICE_WEIGHT), ("systemctl", "thaw", UNIT)]
    assert controls.held == {}


def test_waiting_slots_and_bad_names_are_left_alone():
    calls = Calls()
    follow(steer(calls), [job(state="queued", paused=1), job(runner="../etc", paused=1)])
    assert calls.log == []
