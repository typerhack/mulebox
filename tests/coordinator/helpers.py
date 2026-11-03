"""Helpers shared by the coordinator tests: request building, submitting, queueing."""

import hashlib
import io
import itertools

from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import api, uploads

_counter = itertools.count()


def request(type_: str, **body) -> Message:
    return Message(MessageType(type_), f"req-{next(_counter)}", body)


def submit_body(**extra) -> dict:
    body = {
        "project": "example-app", "job": "check", "argv": ["pnpm", "check"],
        "idempotency_key": f"sub-{next(_counter)}", "fingerprint": "f" * 64,
        "base_commit": "a" * 40, "client": "alice@laptop", "branch": "main",
    }
    body.update(extra)
    return body


def submit(store, staging, now=1000.0, **extra) -> str:
    reply = api.handle(store, staging, request("submit", **submit_body(**extra)), now)
    assert reply.type is MessageType.SUBMIT_OK, reply.body
    return reply.body["job_id"]


def snapshot(data: bytes = b"snapshot bytes") -> tuple[bytes, str]:
    return data, hashlib.sha256(data).hexdigest()


def queued(store, staging, now=1000.0, **extra) -> str:
    """Submit and upload a job so it is `queued`."""
    job_id = submit(store, staging, now, **extra)
    data, digest = snapshot()
    uploads.accept_upload(store, staging, job_id, digest, io.BytesIO(data), now)
    return job_id


def claimed(store, staging, now=1000.0, worker="wrk-a", cluster_slots=10, **extra) -> dict:
    """Queue a job and claim it; return the claim_ok body."""
    queued(store, staging, now, **extra)
    reply = api.handle(store, staging, request(
        "claim", worker=worker, capabilities=["node", "docker"], free_slots=1), now,
        cluster_slots=cluster_slots)
    assert reply.type is MessageType.CLAIM_OK, reply.body
    return reply.body
