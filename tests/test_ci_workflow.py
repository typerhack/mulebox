"""This repository's CI: code from a fork must never reach a self-hosted runner."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
FORK_GUARD = "github.event.pull_request.head.repo.full_name != github.repository"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_every_job_keeps_forks_off_a_self_hosted_runner():
    assert WORKFLOWS
    for path in WORKFLOWS:
        for name, job in _load(path)["jobs"].items():
            runs_on = " ".join(str(job["runs-on"]).split())
            if "self-hosted" in runs_on:
                assert FORK_GUARD in runs_on, f"{path.name}: {name}"
                assert runs_on.index(FORK_GUARD) < runs_on.index("self-hosted")


def test_no_workflow_runs_a_pull_request_with_repository_rights():
    for path in WORKFLOWS:
        workflow = _load(path)
        triggers = workflow.get("on", workflow.get(True))  # YAML reads a bare `on` as true
        assert "pull_request_target" not in triggers, path.name
        assert workflow.get("permissions") == {"contents": "read"}, path.name
