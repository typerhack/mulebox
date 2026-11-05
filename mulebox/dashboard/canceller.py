"""How the dashboard reaches the coordinator for the one thing it writes: `cancel`.

The same request `mulebox cancel` sends, to the same `mulebox rpc`, started here instead of
over ssh. So every rule stays in one place (`coordinator.api.cancel`), and this process keeps
its store read-only: the write happens in a process of its own, gone after one request.
No aiohttp here.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mulebox.client.remote import CoordinatorError, read_reply, request
from mulebox.common.protocol import Message, MessageType, encode

TIMEOUT_S = 30.0


def rpc_command(config_path: Path | None) -> tuple[str, ...]:
    """This installation's `mulebox rpc`, with the node.toml the dashboard itself was given."""
    node = ("--node-config", str(config_path)) if config_path else ()
    return (sys.executable, "-m", "mulebox.cli", "rpc", *node)


class Canceller:
    def __init__(self, config_path: Path | None = None, *, timeout_s: float = TIMEOUT_S,
                 command: tuple[str, ...] | None = None) -> None:
        self.command = command or rpc_command(config_path)
        self.timeout_s = timeout_s

    async def cancel(self, job_id: str) -> Message:
        """The `status_ok` reply. A failure raises CoordinatorError, with `code` when it is
        the coordinator's own answer. Cancelling twice is harmless, so a caller may retry."""
        msg = request(MessageType.CANCEL, job_id=job_id)
        process = await asyncio.create_subprocess_exec(
            *self.command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(encode(msg)), self.timeout_s)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise CoordinatorError("the coordinator did not answer in time", "timeout") from None
        reply = read_reply(stdout, msg)
        if reply is None:
            raise CoordinatorError(f"mulebox rpc gave no reply (exit {process.returncode})")
        return reply
