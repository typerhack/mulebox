"""Helpers for the runner tests: an agent job that holds the slot, a fake clock."""

import hashlib
import io

from mulebox.common.protocol import MessageType
from mulebox.coordinator import uploads
from mulebox.worker.link import request


def agent_job(link, store, staging) -> dict:
    """Queue and claim one agent job for build-1, so it holds the only slot."""
    reply = link.call(request(
        MessageType.SUBMIT, project="example-app", job="check", argv=["pnpm", "check"],
        idempotency_key="sub-busy", fingerprint="f" * 64, base_commit="a" * 40,
        client="alice@dev machine"))
    data = b"snapshot"
    uploads.accept_upload(store, staging, reply.body["job_id"],
                          hashlib.sha256(data).hexdigest(), io.BytesIO(data), 1000.0)
    claim = link.call(request(MessageType.CLAIM, worker="build-1", capabilities=[],
                              free_slots=1))
    assert claim.type is MessageType.CLAIM_OK, claim.body
    return claim.body


def finish_agent_job(link, claim: dict) -> None:
    reply = link.call(request(MessageType.RESULT, job_id=claim["job_id"],
                              attempt_id=claim["attempt_id"], outcome="passed", exit_code=0,
                              duration_s=1.0))
    assert reply.body["state"] == "finished", reply.body


class Clock:
    """A clock whose sleep only advances time; `on_sleep(clock)` runs after each sleep."""

    def __init__(self, start=500.0, on_sleep=None):
        self.now = start
        self.sleeps = 0
        self.on_sleep = on_sleep

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps += 1
        self.now += seconds
        if self.on_sleep is not None:
            self.on_sleep(self)
