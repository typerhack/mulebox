"""Tail a job's raw `out.log`, redact it, and ship it as `log_chunk` messages.

The raw file is read incrementally and decoded as UTF-8 (`errors="replace"`, with an
incremental decoder so a character split across reads stays intact). The text goes through
`StreamRedactor` before it leaves the worker. Offsets are byte offsets of the redacted
UTF-8 stream; each chunk holds at most 64 KiB and is never cut inside a character.

Chunks are queued and sent in order. A transport failure keeps the queue for the next
attempt (the coordinator skips overlap by offset, so a resend is harmless); an `error`
reply drops the queue, since the coordinator will not take this job's log any more.
"""

from __future__ import annotations

import codecs
from collections import deque
from collections.abc import Callable
from pathlib import Path

from mulebox.common.redact import StreamRedactor
from mulebox.common.protocol import Message, MessageType

MAX_CHUNK_BYTES = 64 * 1024
READ_BYTES = 256 * 1024

Send = Callable[[Message], Message]  # raises LinkError on transport failure
MakeRequest = Callable[..., Message]


def split_utf8(data: bytes, limit: int = MAX_CHUNK_BYTES) -> list[bytes]:
    """Split UTF-8 bytes into pieces of at most limit bytes, on character boundaries."""
    pieces = []
    while len(data) > limit:
        cut = limit
        while cut > 0 and (data[cut] & 0xC0) == 0x80:  # continuation byte
            cut -= 1
        pieces.append(data[:cut])
        data = data[cut:]
    if data:
        pieces.append(data)
    return pieces


class LogTailer:
    def __init__(self, path: Path | None, job_id: str, attempt_id: str, make_request: MakeRequest,
                 redactor: StreamRedactor | None = None) -> None:
        self.path = path
        self.job_id = job_id
        self.attempt_id = attempt_id
        self._request = make_request
        self._redactor = redactor or StreamRedactor()
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._read_pos = 0
        self._offset = 0  # redacted bytes queued so far
        self._queue: deque[tuple[int, bytes]] = deque()
        self.dropped = False

    @property
    def sent_all(self) -> bool:
        return not self._queue

    def read_new(self) -> None:
        """Read what was appended to the raw log and queue its redacted text."""
        if self.path is None:
            return
        try:
            with open(self.path, "rb") as fh:
                fh.seek(self._read_pos)
                while chunk := fh.read(READ_BYTES):
                    self._read_pos += len(chunk)
                    self._queue_text(self._redactor.feed(self._decoder.decode(chunk)))
        except FileNotFoundError:
            pass

    def note(self, text: str) -> None:
        """Add a worker message (e.g. why the job could not start) to the stream."""
        self._queue_text(self._redactor.feed(text))

    def finish(self) -> None:
        """Read the rest and release everything the redactor still holds."""
        self.read_new()
        self._queue_text(self._redactor.feed(self._decoder.decode(b"", final=True)))
        self._queue_text(self._redactor.flush())

    def _queue_text(self, text: str) -> None:
        if not text or self.dropped:
            return
        for piece in split_utf8(text.encode("utf-8")):
            self._queue.append((self._offset, piece))
            self._offset += len(piece)

    def send(self, send: Send) -> None:
        """Send queued chunks in order; LinkError propagates and keeps the queue."""
        while self._queue:
            offset, piece = self._queue[0]
            reply = send(self._request(
                MessageType.LOG_CHUNK, job_id=self.job_id, offset=offset,
                data=piece.decode("utf-8"), attempt_id=self.attempt_id))
            if reply.type is MessageType.ERROR:
                self._queue.clear()
                self.dropped = True
                return
            self._queue.popleft()
