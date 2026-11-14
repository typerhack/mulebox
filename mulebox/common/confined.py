"""The confinement every container mulebox runs untrusted code in shares: an isolated runner's
place (runners/place_container.py) and an isolated job (worker/isolated.py).

No capability (`--cap-drop ALL`), `no-new-privileges` (a setuid binary in the image gains
nothing), a limit on processes and on memory (three quarters of the node's), and half Docker's
CPU weight, as a mulebox job unit has half of systemd's. Nothing here mounts or connects
anything: what a container may see is its caller's to name.
"""

from __future__ import annotations

import os

PIDS = 4096
CPU_SHARES = 512  # half Docker's default, as CPUWeight=50 is half systemd's


def memory_limit_mb(total_bytes: int | None = None) -> int:
    if total_bytes is None:
        try:
            total_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError):
            total_bytes = 8 * 1024 ** 3
    return max(1024, int(total_bytes * 3 / 4) // (1024 * 1024))


def run_args(memory_mb: int | None = None) -> list[str]:
    """`docker run` options that confine a container, whatever else it is given."""
    return ["--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", str(PIDS), "--memory", f"{memory_mb or memory_limit_mb()}m",
            "--cpu-shares", str(CPU_SHARES)]
