"""The real-Docker drill stays honest without one: it refuses to run by accident."""

import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).parent.parent / "tools" / "drill_compose.py"


def test_it_will_not_touch_docker_unless_told_to():
    done = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True)
    assert done.returncode == 2 and "--real-docker" in done.stderr


def test_it_only_removes_through_the_workers_teardown():
    text = TOOL.read_text()
    assert "docker_cleanup.teardown(" in text
    for word in ('"rm"', '"prune"', '"system"', "rmi"):
        assert word not in text
