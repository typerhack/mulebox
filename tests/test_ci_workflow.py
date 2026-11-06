"""The repository's workflow stays safe for a public repository, and on the minimum Python.

This keeps honest edits honest. It cannot stop a hostile pull request, which can change this
test too: that protection is having no self-hosted runner at all (docs/releasing.md).
"""

import importlib.util
import re
import tomllib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.yml"))
FULL_COMMIT = re.compile(r"^[\w./-]+@[0-9a-f]{40}$")


def load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["on"] = data.pop(True)  # YAML reads the key `on` as a boolean
    return data


def steps(workflow: dict) -> list[dict]:
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def test_there_is_a_workflow():
    assert WORKFLOWS


def test_only_github_hosted_machines():
    for path in WORKFLOWS:
        assert "self-hosted" not in yaml.safe_dump(load(path)["jobs"]), path
        for job in load(path)["jobs"].values():
            machines = job.get("strategy", {}).get("matrix", {}).get("os", [job["runs-on"]])
            for machine in machines:
                assert re.fullmatch(r"(ubuntu|macos)-[\d.]+", machine), path  # no ${{ }} either


def test_no_trigger_gives_a_fork_secrets_or_write_access():
    for path in WORKFLOWS:
        assert not {"pull_request_target", "workflow_run"} & set(load(path)["on"]), path


def test_the_token_is_read_only_and_not_kept():
    for path in WORKFLOWS:
        workflow = load(path)
        assert workflow["permissions"] == {"contents": "read"}, path
        checkouts = [s for s in steps(workflow) if s.get("uses", "").startswith("actions/checkout")]
        assert checkouts and all(s["with"]["persist-credentials"] is False for s in checkouts)


def test_actions_are_pinned_to_a_full_commit():
    for path in WORKFLOWS:
        for step in steps(load(path)):
            assert "uses" not in step or FULL_COMMIT.match(step["uses"]), step


def test_it_runs_the_gate_on_the_minimum_python():
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    minimum = pyproject["project"]["requires-python"].removeprefix(">=")
    workflow = load(REPO / ".github" / "workflows" / "ci.yml")
    assert workflow["jobs"]["test"]["strategy"]["matrix"]["python"][0] == minimum
    commands = " ".join(step.get("run", "") for step in steps(workflow))
    assert "tools/check_line_counts.py" in commands and "pytest" in commands


def test_a_release_runs_on_tags_alone_and_gives_only_its_upload_the_token():
    workflow = load(REPO / ".github" / "workflows" / "release.yml")
    assert workflow["on"] == {"push": {"tags": ["v*"]}}
    with_token = [step for step in steps(workflow) if "GH_TOKEN" in step.get("env", {})]
    assert [step["name"] for step in with_token] == ["Open a draft release",
                                                     "Upload to the draft release"]
    assert "--draft" in with_token[0]["run"]
    assert workflow["jobs"]["build"]["steps"][-1] is with_token[1]


def test_a_release_file_is_named_for_its_system():
    spec = importlib.util.spec_from_file_location("build_binary", REPO / "tools" / "build_binary.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert tool.archive_name("1.0.0", "Darwin", "arm64") == "mulebox-1.0.0-macos-arm64.tar.gz"
    assert tool.archive_name("1.0.0", "Linux", "x86_64") == "mulebox-1.0.0-linux-x86_64.tar.gz"
