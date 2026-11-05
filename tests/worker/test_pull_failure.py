"""A registry out of reach is not a failed check."""

import pytest

from mulebox.common.protocol import Outcome
from mulebox.common.status import IMAGES, NOT_STARTED_NOTE, SERVICES
from mulebox.worker import pull_failure
from mulebox.worker.logtail import LogTailer
from mulebox.worker.steps import StepTracker

REFUSED = ('Error response from daemon: failed to resolve reference "127.0.0.1:1/x:1": failed to '
           'do request: Head "https://127.0.0.1:1/v2/x/manifests/1": dial tcp 127.0.0.1:1: '
           'connect: connection refused')
NO_HOST = ('Error response from daemon: failed to resolve reference "registry.invalid/x:1": '
           'dial tcp: lookup registry.invalid: no such host')
DENIED = "denied"  # what a real pull of a name that does not exist ended with
BUILD = ('target app: failed to solve: process "/bin/sh -c curl dial tcp" did not complete '
         'successfully: exit code: 7')


@pytest.mark.parametrize("line", [
    REFUSED, NO_HOST, "net/http: TLS handshake timeout", "read: connection reset by peer",
    "toomanyrequests: You have reached your pull rate limit",
    "received unexpected HTTP status: 503 Service Unavailable",
])
def test_network_failures_are_told_apart(line):
    assert pull_failure.network_failed(IMAGES, line)


@pytest.mark.parametrize("line", [DENIED, BUILD, "manifest unknown", "", None])
def test_other_failures_of_the_images_stage_stay_failures(line):
    assert not pull_failure.network_failed(IMAGES, line)


def test_only_the_images_stage_counts():
    assert not pull_failure.network_failed(SERVICES, REFUSED)
    assert not pull_failure.network_failed(None, REFUSED)


def finished(tmp_path, *lines):
    log = tmp_path / "out.log"
    steps = StepTracker()
    steps.begin(IMAGES, 1.0)
    tailer = LogTailer(log, "job-1", "att-1", lambda *a, **k: None, steps=steps)
    log.write_text("".join(f"{line}\n" for line in lines))
    tailer.finish()
    return tailer


def test_a_failed_pull_has_no_exit_code_and_says_why(tmp_path):
    tailer = finished(tmp_path, " Image x Pulling", REFUSED)
    assert pull_failure.checked(Outcome.FAILED, 1, tailer) is None
    assert f"{NOT_STARTED_NOTE} {pull_failure.REASON}" in b"".join(piece for _, piece in tailer._queue).decode()


def test_a_project_failure_keeps_its_code(tmp_path):
    tailer = finished(tmp_path, BUILD)
    assert pull_failure.checked(Outcome.FAILED, 17, tailer) == 17


def test_only_a_failed_job_is_looked_at(tmp_path):
    tailer = finished(tmp_path, REFUSED)
    assert pull_failure.checked(Outcome.CANCELLED, 130, tailer) == 130
