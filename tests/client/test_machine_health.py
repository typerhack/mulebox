"""A node's health in `mulebox machine list` and `machine check` (client/machine_health.py),
and when a disk counts as low (common/disk.py)."""

from mulebox.client import machine_commands, machine_health
from mulebox.common import disk

DOCKER = {"resting": False, "withheld": ["docker"], "round": 1,
          "problems": [{"check": "docker", "message": "Docker does not answer",
                        "fix": "start Docker on build-1", "since": 0.0}]}


def test_the_state_says_resting_or_what_is_held_back():
    assert machine_health.state(None) is None
    assert machine_health.state({"resting": False, "problems": [], "round": 3}) is None
    assert machine_health.state(DOCKER) == "no docker"
    assert machine_health.state({**DOCKER, "resting": True}) == "resting"
    row = {"online": True, "health": {**DOCKER, "resting": True}}
    assert machine_commands.state(row) == "resting"
    assert machine_commands.state({**row, "online": False}) == "offline"
    assert machine_commands.state({**row, "draining": True}) == "draining"


def test_problem_lines_give_the_fix():
    lines = machine_health.problem_lines("build-1", DOCKER)
    assert lines[0].startswith("  build-1: Docker does not answer (since ")
    assert lines[1] == "    fix: start Docker on build-1"
    assert machine_health.problem_lines("build-1", None) == []


def test_a_disk_is_low_under_a_tenth_or_10_gb_whichever_is_more():
    tb = 1_000_000_000_000
    assert disk.is_low(90_000_000_000, tb) and not disk.is_low(110_000_000_000, tb)
    assert disk.is_low(9_000_000_000, 50_000_000_000)  # a small disk: 10 GB still counts
    assert not disk.is_low(11_000_000_000, None)
    assert "(9% of its disk)" in disk.warning("build-1", 90_000_000_000, tb)
