"""Test doubles for the worker: tar builder, claim bodies, a fake coordinator link."""

import io
import tarfile
from pathlib import Path

from mulebox.common.ids import new_id
from mulebox.common.protocol import Message, MessageType
from mulebox.worker.link import LinkError


def make_tar(path: Path, files: dict[str, str | bytes], mode: str = "w:gz") -> Path:
    """Write a tar archive with the given regular files."""
    with tarfile.open(path, mode) as tar:
        for name, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return path


class FakeLink:
    """Records every request and plays coordinator replies."""

    def __init__(self, snapshot: Path | None = None) -> None:
        self.snapshot = snapshot
        self.sent: list[Message] = []
        self.claims: list[dict] = []
        self.down = False
        self.cancel = False
        self.heartbeat_state = "running"
        self.refuse: set[MessageType] = set()

    def call(self, msg: Message) -> Message:
        if self.down:
            raise LinkError("coordinator unreachable (fake)")
        self.sent.append(msg)
        if msg.type in self.refuse:
            return Message(MessageType.ERROR, msg.request_id,
                           {"code": "conflict", "message": "refused (fake)"})
        if msg.type is MessageType.CLAIM:
            if not self.claims:
                return Message(MessageType.CLAIM_NONE, msg.request_id, {})
            return Message(MessageType.CLAIM_OK, msg.request_id, self.claims.pop(0))
        body = {"job_id": msg.body.get("job_id", "x"), "state": self.heartbeat_state}
        if msg.type is MessageType.HEARTBEAT:
            body["cancel"] = self.cancel
        if msg.type is MessageType.JOB_UPDATE:
            body["state"] = msg.body["state"]
        return Message(MessageType.STATUS_OK, msg.request_id, body)

    def fetch_snapshot(self, job_id: str, dest: Path) -> None:
        if self.down:
            raise LinkError("coordinator unreachable (fake)")
        dest.write_bytes(self.snapshot.read_bytes())

    def of_type(self, kind: MessageType) -> list[Message]:
        return [m for m in self.sent if m.type is kind]

    def log_text(self) -> str:
        chunks = sorted((m.body["offset"], m.body["data"]) for m in self.of_type(MessageType.LOG_CHUNK))
        return "".join(data for _, data in chunks)


def claim_body(argv, *, timeout_min=1, setup=None, toolchain=None, project="example-app"):
    return {
        "job_id": new_id("job"), "attempt_id": new_id("att"), "project": project,
        "argv": list(argv), "fingerprint": "f" * 64, "base_commit": "0" * 40,
        "timeout_min": timeout_min, "setup": setup, "toolchain": toolchain or {},
        "needs": [], "job": "check",
    }
