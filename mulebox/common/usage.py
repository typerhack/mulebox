"""What one run used at most: its busiest cores and its largest memory (docs/design.md, Job usage).

The worker and the GitHub supervisor feed a `Peaks` one reading at a time (every 10 s, the job
meter's sample): the cores the run kept busy since the reading before, and the memory it held
then. It keeps the highest of each, the stage it came in, and the CPU seconds in all. `as_dict` is
what travels as `usage` in heartbeats and results and is kept in `jobs.usage`.

A reading that is unknown is left out, never counted as 0: a run with no cores reading has
`peak_cores` None ("too short to measure"), and a run from a worker that sends nothing has no
`usage` at all ("not measured").
"""

from __future__ import annotations

from typing import Any

STAGE_CHARS = 80
KEYS = ("peak_cores", "peak_cores_stage", "peak_memory", "peak_memory_stage", "cpu_s", "samples")


class Peaks:
    def __init__(self) -> None:
        self.peak_cores: float | None = None
        self.peak_cores_stage: str | None = None
        self.peak_memory: int | None = None
        self.peak_memory_stage: str | None = None
        self.cpu_s = 0.0
        self.samples = 0

    def add(self, cores: float | None, memory: int | None, stage: str | None,
            cpu_s: float | None = None) -> None:
        """One reading: `cores` busy over its span, `memory` bytes held now, `cpu_s` used in it."""
        if cores is None and memory is None:
            return
        self.samples += 1
        if cpu_s is not None and cpu_s > 0:
            self.cpu_s += cpu_s
        if cores is not None and (self.peak_cores is None or cores > self.peak_cores):
            self.peak_cores, self.peak_cores_stage = round(cores, 2), stage
        if memory is not None and (self.peak_memory is None or memory > self.peak_memory):
            self.peak_memory, self.peak_memory_stage = int(memory), stage

    def as_dict(self) -> dict[str, Any] | None:
        """None until a reading came: nothing measured yet."""
        if not self.samples:
            return None
        return {"peak_cores": self.peak_cores, "peak_cores_stage": self.peak_cores_stage,
                "peak_memory": self.peak_memory, "peak_memory_stage": self.peak_memory_stage,
                "cpu_s": round(self.cpu_s, 1), "samples": self.samples}


def clean(report: Any) -> dict[str, Any] | None:
    """A `usage` a worker sent, with only known keys of the right type; None if it is not one."""
    if not isinstance(report, dict):
        return None
    out: dict[str, Any] = {}
    for key in ("peak_cores", "cpu_s"):
        value = report.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 1e9:
            out[key] = float(value)
    for key in ("peak_memory", "samples"):
        value = report.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 1 << 50:
            out[key] = value
    for key in ("peak_cores_stage", "peak_memory_stage"):
        value = report.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()[:STAGE_CHARS]  # a GitHub run's step name can be long
    return out if out.get("samples") else None


def average_cores(usage: dict[str, Any] | None, run_s: float | None) -> float | None:
    """CPU seconds over the run's length; None where either is unknown."""
    if not usage or not run_s or run_s <= 0 or "cpu_s" not in usage:
        return None
    return round(usage["cpu_s"] / run_s, 2)
