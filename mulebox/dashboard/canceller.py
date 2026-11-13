"""How the dashboard reaches the coordinator for what it writes: `cancel`, a job's controls
(`job_control`) and pausing a machine (`machine`).

The same requests `mulebox cancel`, `mulebox pause` and `mulebox machine pause` send, to the
same `mulebox rpc`, started here instead of over ssh. So every rule stays in one place (`coordinator.api.cancel`), and this process keeps
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
        return await self.send(request(MessageType.CANCEL, job_id=job_id))

    async def control(self, job_id: str, action: str) -> Message:
        """`job_control` (coordinator/job_control.py); its `status_ok` reply."""
        return await self.send(request(MessageType.JOB_CONTROL, job_id=job_id, action=action))

    async def machine(self, worker: str, action: str) -> Message:
        """`machine` drain or resume (coordinator/machine_api.py); its `machine_ok` reply."""
        return await self.send(request(MessageType.MACHINE, worker=worker, action=action))

    async def node_settings(self, worker: str, **change: object) -> Message:
        """`node_settings` with `slots`, `priority` or `cancel` (coordinator/node_settings.py);
        its `node_settings_ok` reply."""
        return await self.send(request(MessageType.NODE_SETTINGS, worker=worker, **change))

    async def send(self, msg: Message) -> Message:
        """One request through a `mulebox rpc` of its own; its reply, or CoordinatorError."""
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
