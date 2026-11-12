"""The machine's own readings on macOS, in the shapes host.py gives on Linux.

- CPU: each core's ticks from the kernel (`host_processor_info`, through ctypes): user, system,
  idle and nice, at 100 a second. macOS has no iowait, so busy is everything but idle.
- Memory: `hw.memsize` and `vm_stat`. Available is free, inactive and speculative pages, which
  macOS hands out again at once, as Linux's MemAvailable counts its page cache.
- Swap: `vm.swapusage`.
- Network: `netstat -ibn`, the `en*` interfaces only (Wi-Fi, Ethernet, Thunderbolt ports): a VPN's
  `utun`, Docker's and the Thunderbolt `bridge`, `awdl` and loopback are left out, as on Linux
  (common/netdev.py), so no byte counts twice.

Each reader gives None when its source cannot be read; the parsers are plain functions of the
commands' text, so they are tested on any system.
"""

from __future__ import annotations

import ctypes
import re
import sys
from typing import Any

from mulebox.common import command

TICKS_PER_S = 100  # CLK_TCK on macOS
CPU_STATES = 4  # user, system, idle, nice
IDLE = 2
_PROCESSOR_CPU_LOAD_INFO = 2
_PAGE_SIZE = re.compile(r"page size of (\d+) bytes")
_PAGES = re.compile(r'^"?([A-Za-z ]+?)"?:\s+(\d+)\.?$')
_SWAP = re.compile(r"(total|used) = ([\d.]+)([KMGT])")
_UNITS = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30, "T": 1 << 40}
_PHYSICAL = re.compile(r"en\d+")


def _sysctl(name: str) -> str | None:
    try:
        done = command.run(["sysctl", "-n", name], timeout_s=10)
    except command.CommandError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _output(argv: list[str]) -> str | None:
    try:
        done = command.run(argv, timeout_s=10)
    except command.CommandError:
        return None
    return done.stdout if done.returncode == 0 else None


def core_ticks() -> list[list[int]] | None:
    """[user, system, idle, nice] ticks of each core; None off macOS or when the call fails."""
    if sys.platform != "darwin":
        return None
    try:
        libc = ctypes.CDLL("/usr/lib/libSystem.dylib")
        host = ctypes.c_uint(libc.mach_host_self())
        count, info, size = ctypes.c_uint(), ctypes.POINTER(ctypes.c_int)(), ctypes.c_uint()
        if libc.host_processor_info(host, _PROCESSOR_CPU_LOAD_INFO, ctypes.byref(count),
                                    ctypes.byref(info), ctypes.byref(size)) != 0:
            return None
        try:
            values = [info[i] for i in range(count.value * CPU_STATES)]
        finally:
            task = ctypes.c_uint.in_dll(libc, "mach_task_self_")
            libc.vm_deallocate(task, ctypes.cast(info, ctypes.c_void_p),
                               ctypes.c_size_t(size.value * ctypes.sizeof(ctypes.c_int)))
    except (OSError, AttributeError, ValueError):
        return None
    return [[v & 0xFFFFFFFF for v in values[i:i + CPU_STATES]]
            for i in range(0, len(values), CPU_STATES)]


def parse_vm_stat(text: str, total: int) -> dict[str, int] | None:
    """total, available and used bytes from `vm_stat` and `hw.memsize`."""
    size = _PAGE_SIZE.search(text)
    if not size or total <= 0:
        return None
    pages = {}
    for line in text.splitlines():
        match = _PAGES.match(line.strip())
        if match:
            pages[match.group(1).strip().lower()] = int(match.group(2))
    try:
        free = sum(pages[f"pages {kind}"] for kind in ("free", "inactive", "speculative"))
    except KeyError:
        return None
    available = min(total, free * int(size.group(1)))
    return {"total": total, "available": available, "used": total - available}


def parse_swapusage(text: str) -> dict[str, int] | None:
    found = {key: int(float(value) * _UNITS[unit]) for key, value, unit in _SWAP.findall(text)}
    if set(found) != {"total", "used"}:
        return None
    return {"total": found["total"], "used": found["used"]}


def parse_netstat(text: str) -> tuple[int, int] | None:
    """Bytes in and out over the `en*` interfaces, from their `<Link#n>` lines."""
    rx = tx = 0
    found = False
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 10 or not fields[2].startswith("<Link#"):
            continue
        if not _PHYSICAL.fullmatch(fields[0].rstrip("*")):
            continue
        first = 6 if len(fields) >= 11 else 5  # the Address column is empty for some
        try:
            rx, tx, found = rx + int(fields[first]), tx + int(fields[first + 3]), True
        except (ValueError, IndexError):
            continue
    return (rx, tx) if found else None


def memory() -> dict[str, int] | None:
    total, text = _sysctl("hw.memsize"), _output(["vm_stat"])
    if not total or not total.isdigit() or text is None:
        return None
    return parse_vm_stat(text, int(total))


def swap() -> dict[str, int] | None:
    text = _sysctl("vm.swapusage")
    return parse_swapusage(text) if text else None


def net() -> tuple[int, int] | None:
    text = _output(["netstat", "-ibn"])
    return parse_netstat(text) if text else None


def readings() -> dict[str, Any]:
    """Everything at once, for a look by hand: `python -m mulebox.common.darwin_host`."""
    return {"cores": core_ticks(), "memory": memory(), "swap": swap(), "net": net()}


if __name__ == "__main__":
    print(readings())
