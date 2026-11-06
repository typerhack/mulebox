"""The `install` line of `.mulebox.yml`: what fills a project's folder, as a stage of its own.

It runs in the job's script, after the containers are up, so it can run inside the project's own
image with `docker compose exec`. A failure that reads like the network is tried again, as a
dropped download says nothing about the project. Any failure there is reported apart from the
job's code: the job never got to run (`checked`). The worker keeps the line from running again
until something it depends on changes (project_home.install_key).
"""

from __future__ import annotations

import shlex

from mulebox.common.network_errors import REGISTRY
from mulebox.common.protocol import Outcome
from mulebox.common.status import INSTALL, NOT_STARTED_NOTE
from mulebox.worker.logtail import LogTailer

TRIES = 3
WAIT_S = 5  # times the try: 5 s, then 10 s
LINES_READ = 6  # as in the failure summary: a failure earlier in the output was survived
REASON = "the project's `install` failed, so its code did not run"


def script_lines(line: str) -> list[str]:
    """Bash lines running `line`; `set -e` is on in it, and the job stops on its exit code."""
    return [
        "mulebox_install() {",
        "  local try code out",
        f"  for try in {' '.join(str(n) for n in range(1, TRIES + 1))}; do",
        "    out=$(mktemp)",
        '    bash -e -c "$1" 2>&1 | tee "$out"',
        "    code=${PIPESTATUS[0]}",
        '    if [ "$code" -eq 0 ]; then rm -f "$out"; return 0; fi',
        f'    if [ "$try" -lt {TRIES} ] && tail -n {LINES_READ} "$out" '
        f"| grep -Eiq {shlex.quote(REGISTRY.pattern)}; then",
        f'      echo "mulebox: install lost its network, trying again in $((try * {WAIT_S})) s"',
        f'      rm -f "$out"; sleep $((try * {WAIT_S}))',
        '    else rm -f "$out"; return "$code"; fi',
        "  done",
        "}",
        f"mulebox_install {shlex.quote(line)}",
    ]


def checked(outcome: Outcome, exit_code: int | None, tailer: LogTailer) -> int | None:
    """The code to report, after `tailer.finish()`. None: the job never ran."""
    if outcome is not Outcome.FAILED or tailer.steps.stage != INSTALL:
        return exit_code
    tailer.note(f"{NOT_STARTED_NOTE} {REASON}\n")
    tailer.finish()
    return None
