"""Pause and boost applied to a running job on the worker (worker/controls.py, M14.3)."""

from types import SimpleNamespace

from mulebox.worker.controls import BOOST_SHARES, NORMAL_SHARES, JobControls
from mulebox.worker.docker import DockerError


class Calls:
    """A stand-in executor and docker that write down what was asked, in order."""

    def __init__(self, ids=("c1",), fail_unpause=False):
        self.log, self.ids, self.fail_unpause = [], list(ids), fail_unpause

    def freeze(self, handle, on):
        self.log.append(("freeze" if on else "thaw", handle))

    def prioritize(self, handle, on):
        self.log.append(("weight", on))

    def lines(self, *args):
        return self.ids

    def run(self, *args):
        if args[0] == "unpause" and self.fail_unpause:
            raise DockerError("not paused")
        self.log.append(tuple(args))
        return ""


def follow(controls, body, job, calls):
    controls.follow(body, job, calls, calls)
    assert controls.task is None or controls.task.wait(5.0)
    assert controls.task is None or controls.task.error is None, controls.task.error


def job(handle="unit"):
    return SimpleNamespace(job_id="job-1", handle=handle)


def test_pause_freezes_then_resume_unpauses_before_thawing():
    calls, controls, running = Calls(), JobControls(), job()
    follow(controls, {"paused": True}, running, calls)
    assert calls.log == [("freeze", "unit"), ("pause", "c1")]
    follow(controls, {"paused": True}, running, calls)  # already so: nothing again
    assert len(calls.log) == 2
    follow(controls, {}, running, calls)
    assert calls.log[2:] == [("unpause", "c1"), ("thaw", "unit")]


def test_boost_raises_weights_each_reply_and_normal_restores_them():
    calls, controls, running = Calls(), JobControls(), job()
    follow(controls, {"boost": True}, running, calls)
    follow(controls, {"boost": True}, running, calls)  # containers that came up since
    assert calls.log == [("weight", True), ("update", "--cpu-shares", str(BOOST_SHARES), "c1")] * 2
    follow(controls, {}, running, calls)
    assert calls.log[4:] == [("weight", False), ("update", "--cpu-shares", str(NORMAL_SHARES), "c1")]


def test_nothing_before_the_unit_starts():
    calls, controls = Calls(), JobControls()
    follow(controls, {"paused": True}, job(handle=None), calls)
    assert calls.log == [] and controls.task is None


def test_release_resumes_a_paused_job_before_its_stop_even_if_a_container_is_gone():
    calls, controls, running = Calls(ids=("c1", "c2")), JobControls(), job()
    follow(controls, {"paused": True}, running, calls)
    calls.fail_unpause = True
    controls.release(running, calls, calls)
    assert calls.log[-1] == ("thaw", "unit")
    assert not controls.applied.paused
