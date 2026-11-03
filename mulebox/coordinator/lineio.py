"""Line I/O for the rpc entry points: capped reads, one-line writes, error notes."""

from typing import BinaryIO, TextIO

from mulebox.common.protocol import MAX_LINE_BYTES, Message, MessageType, encode
from mulebox.coordinator.errors import TooLarge


def read_line(stream: BinaryIO) -> bytes | None:
    """One line of at most MAX_LINE_BYTES; None at end of input; TooLarge past the cap."""
    line = stream.readline(MAX_LINE_BYTES + 1)
    if not line:
        return None
    if len(line) > MAX_LINE_BYTES:
        raise TooLarge(f"request line exceeds {MAX_LINE_BYTES} bytes")
    return line


def write_message(stream: BinaryIO, msg: Message) -> None:
    stream.write(encode(msg))
    stream.flush()


def note_error(stderr: TextIO | None, msg: Message) -> None:
    """Repeat an error reply on stderr, so a caller that only sees stderr learns why."""
    if stderr is None or msg.type is not MessageType.ERROR:
        return
    try:
        stderr.write(f"mulebox: error {msg.body['code']}: {msg.body['message']}\n")
        stderr.flush()
    except (OSError, ValueError):
        pass
