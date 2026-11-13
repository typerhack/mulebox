"""Start a program on macOS as its own responsible process, for ssh from a launchd service.

macOS asks a person before a program reaches the local network, and for a launchd agent it asks
about the agent's program: Homebrew's Python, which it never shows a prompt for and refuses with
`No route to host` (seen on a Mac node, 2026-11-13). Apple's own `ssh`, started as its own
responsible process ("disclaimed"), is let through, as Terminal does for the shell it starts.

`prefix()` is what `common/ssh.py` puts before `ssh`: nothing on Linux or outside a mulebox
service (the launchd plist sets MULEBOX_SERVICE=launchd), else `python -m mulebox.common.disclaim`.
`main()` spawns the rest of its argv with `responsibility_spawnattrs_setdisclaim`, gives it its
own stdin, stdout and stderr, passes on SIGTERM, SIGINT and SIGHUP, and exits with its code.
"""

from __future__ import annotations

import ctypes
import os
import signal
import sys
from collections.abc import Mapping, Sequence

SERVICE_ENV = "MULEBOX_SERVICE"
_FORWARDED = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)


def needed(platform: str = sys.platform, environ: Mapping[str, str] = os.environ) -> bool:
    return platform == "darwin" and environ.get(SERVICE_ENV) == "launchd"


def prefix(platform: str = sys.platform, environ: Mapping[str, str] = os.environ) -> list[str]:
    return [sys.executable, "-m", "mulebox.common.disclaim"] if needed(platform, environ) else []


def _c_strings(items: Sequence[str]):
    raw = [item.encode() for item in items]
    return (ctypes.c_char_p * (len(raw) + 1))(*raw, None)


def spawn(argv: Sequence[str]) -> int:
    """posix_spawnp `argv` disclaimed; return its pid. Raises OSError if it cannot start."""
    libc = ctypes.CDLL(None, use_errno=True)
    attr = ctypes.c_void_p()
    if libc.posix_spawnattr_init(ctypes.byref(attr)) != 0:
        raise OSError("posix_spawnattr_init failed")
    try:
        code = libc.responsibility_spawnattrs_setdisclaim(ctypes.byref(attr), 1)
        if code != 0:
            raise OSError(code, "cannot disclaim responsibility")
        pid = ctypes.c_int()
        env = [f"{key}={value}" for key, value in os.environ.items()]
        code = libc.posix_spawnp(ctypes.byref(pid), argv[0].encode(), None, ctypes.byref(attr),
                                 _c_strings(argv), _c_strings(env))
        if code != 0:
            raise OSError(code, f"cannot start {argv[0]}: {os.strerror(code)}")
        return pid.value
    finally:
        libc.posix_spawnattr_destroy(ctypes.byref(attr))


def main(argv: Sequence[str]) -> int:
    if not argv:
        print("usage: python -m mulebox.common.disclaim <program> [args...]", file=sys.stderr)
        return 2
    try:
        pid = spawn(argv)
    except OSError as exc:
        print(f"mulebox: {exc}", file=sys.stderr)
        return 255  # as ssh does when it cannot connect
    for sig in _FORWARDED:
        signal.signal(sig, lambda number, _frame: os.kill(pid, number))
    while True:
        try:
            _, status = os.waitpid(pid, 0)
            return os.WEXITSTATUS(status) if os.WIFEXITED(status) else 128 + os.WTERMSIG(status)
        except InterruptedError:
            continue


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
