"""Tail a job's raw `out.log`, redact it, and ship it as `log_chunk` messages.

The raw file is read incrementally and decoded as UTF-8 (`errors="replace"`, with an
incremental decoder so a character split across reads stays intact). The text goes through
`StreamRedactor` before it leaves the worker. Offsets are byte offsets of the redacted
UTF-8 stream; each chunk holds at most 64 KiB and is never cut inside a character.

Redacted text then goes on line by line: DownloadWatch (common/download_watch.py) reads what is
downloading and how far it got, PullNoise (pullnoise.py) collapses image progress, and the job's
StepTracker takes out the stage marks. So the stored log and the steps only ever
see redacted text. The raw file keeps everything until the job's folder goes.

Chunks are queued and sent in order. A transport failure keeps the queue for the next
attempt (the coordinator skips overlap by offset, so a resend is harmless); an `error`
reply drops the queue, since the coordinator will not take this job's log any more. Stage
rows go the same way, after the log, so a failing line never arrives ahead of its log.
"""

from __future__ import annotations

import codecs
import re
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

from mulebox.common.download_watch import DownloadWatch
from mulebox.common.redact import StreamRedactor
from mulebox.common.protocol import Message, MessageType
from mulebox.worker.pullnoise import PullNoise
from mulebox.worker.steps import StepTracker

MAX_CHUNK_BYTES = 64 * 1024
READ_BYTES = 256 * 1024
MAX_PARTIAL_CHARS = 16 * 1024  # a line longer than this goes on without being looked at
_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+")

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
                 redactor: StreamRedactor | None = None,
                 steps: StepTracker | None = None, watch_downloads: bool = True,
                 clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self.job_id = job_id
        self.attempt_id = attempt_id
        self._request = make_request
        self._redactor = redactor or StreamRedactor()
        self.steps = steps or StepTracker()
        self._noise = PullNoise()
        self.download = DownloadWatch() if watch_downloads else None
        self._clock = clock
        self._partial = ""  # redacted text of a line not finished yet
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._read_pos = 0
        self._offset = 0  # redacted bytes queued so far
        self._queue: deque[tuple[int, bytes]] = deque()
        self.dropped = False

    @property
    def sent_all(self) -> bool:
        return not self._queue

    def read_new(self) -> bool:
        """Read what was appended to the raw log and queue its redacted text; True if any."""
        before = self._read_pos
        if self.path is None:
            return False
        try:
            with open(self.path, "rb") as fh:
                fh.seek(self._read_pos)
                while chunk := fh.read(READ_BYTES):
                    self._read_pos += len(chunk)
                    self._take(self._redactor.feed(self._decoder.decode(chunk)))
        except FileNotFoundError:
            pass
        return self._read_pos > before

    def note(self, text: str) -> None:
        """Add a worker message (e.g. why the job could not start) to the stream."""
        self._take(self._redactor.feed(text))

    def finish(self) -> None:
        """Read the rest and release everything the redactor still holds."""
        self.read_new()
        self._take(self._redactor.feed(self._decoder.decode(b"", final=True)))
        self._take(self._redactor.flush())
        self._take("", final=True)
        self._queue_text("".join(self._noise.flush()))

    def _take(self, text: str, final: bool = False) -> None:
        """Whole lines of redacted text go on; the rest of a line waits for its end."""
        buffer = self._partial + text
        end = max(buffer.rfind("\n"), buffer.rfind("\r")) + 1
        if final or len(buffer) - end > MAX_PARTIAL_CHARS:
            end = len(buffer)
        self._partial = buffer[end:]
        self._queue_text("".join(self._kept(line) for line in _LINE.findall(buffer[:end])))

    def _kept(self, line: str) -> str:
        pieces = self._noise.line(line)
        fresh = self._noise.take_new_bytes()
        self.steps.add_bytes(fresh)
        if self.download is not None:
            at = self._clock()
            self.download.step(self.steps.stage)
            self.download.line(line, at)
            if fresh:
                self.download.image_bytes(self._noise.total, self._noise.size, at)
            if not self._noise.downloading:
                self.download.image_done()
        return "".join(self.steps.line(piece) for piece in pieces)

    def _queue_text(self, text: str) -> None:
        if not text or self.dropped:
            return
        for piece in split_utf8(text.encode("utf-8")):
            self._queue.append((self._offset, piece))
            self._offset += len(piece)

    def send(self, send: Send) -> None:
        """Send queued chunks in order, then stage rows; LinkError propagates and keeps both."""
        self._send_log(send)
        rows = self.steps.pending()
        if rows:
            send(self._request(MessageType.STEPS, job_id=self.job_id, steps=rows,
                               attempt_id=self.attempt_id))
            self.steps.sent()  # also on an error reply: they are a report, never worth a retry

    def _send_log(self, send: Send) -> None:
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
