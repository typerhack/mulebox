"""`mulebox dashboard open`: an SSH tunnel to the dashboard, then the browser.

Runs `ssh -N -L 127.0.0.1:<local>:127.0.0.1:<remote> <coordinator>` (common/ssh.py
`tunnel_argv`), waits until `http://127.0.0.1:<local>/healthz` answers through it, opens
the browser and keeps the tunnel until Ctrl-C or until ssh exits. The process, the
health probe, the browser and the clock are injectable for tests.
"""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from typing import TextIO

from mulebox.client import report
from mulebox.common import ssh
from mulebox.common.config import ClientConfig

PROBE_EVERY_S = 0.25
EXTRA_WAIT_S = 5.0  # on top of the ssh connect timeout
TERMINATE_GRACE_S = 5.0


def healthy(url: str) -> bool:
    """True when the dashboard answers `/healthz` at `url`."""
    try:
        with urllib.request.urlopen(f"{url}/healthz", timeout=2) as reply:
            return reply.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def open_dashboard(
    config: ClientConfig, local_port: int, remote_port: int, out: TextIO, *,
    browser: bool = True,
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
    probe: Callable[[str], bool] = healthy,
    opener: Callable[[str], object] = webbrowser.open,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    argv = ssh.tunnel_argv(config.coordinator, local_port, remote_port,
                           config.connect_timeout_s)
    url = f"http://127.0.0.1:{local_port}"
    try:
        proc = popen(argv, stdin=subprocess.DEVNULL)
    except OSError as exc:
        raise ssh.cannot_start(exc) from exc
    try:
        deadline = clock() + config.connect_timeout_s + EXTRA_WAIT_S
        while not probe(url):
            if proc.poll() is not None:
                report.status(out, f"error: the ssh tunnel to {config.coordinator} closed "
                              f"(exit {proc.returncode}); is local port {local_port} in use? "
                              "Try --port.")
                return report.EXIT_UNREACHABLE
            if clock() >= deadline:
                report.status(out, f"error: no dashboard answers on port {remote_port} of "
                              f"{config.coordinator}. Check `mulebox service status "
                              "dashboard` there (and the port in node.toml).")
                return report.EXIT_UNREACHABLE
            sleep(PROBE_EVERY_S)
        report.status(out, f"dashboard at {url} (Ctrl-C closes the tunnel)")
        if browser:
            opener(url)
        code = proc.wait()
        report.status(out, f"the ssh tunnel closed (exit {code})")
        return report.EXIT_UNREACHABLE
    except KeyboardInterrupt:
        return 0
    finally:
        _stop(proc)


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=TERMINATE_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
