"""The repository's workflow stays safe for a public repository, and on the minimum Python.

This keeps honest edits honest. It cannot stop a hostile pull request, which can change this
test too: that protection is having no self-hosted runner at all (docs/releasing.md).
"""

import importlib.util
import json
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


def test_the_web_front_end_has_its_own_gate_and_is_built_into_a_release():
    web = load(REPO / ".github" / "workflows" / "ci.yml")["jobs"]["web"]
    commands = [step.get("run", "") for step in web["steps"]]
    assert web["defaults"]["run"]["working-directory"] == "web"
    for needed in ("npm ci", "npm run lint", "npm run typecheck", "npm test", "npm run build"):
        assert any(needed in command for command in commands), needed
    scripts = json.loads((REPO / "web" / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert "check-classes.mjs" in scripts["lint"]  # no value typed in beside the design tokens
    names = [step.get("name") for step in load(REPO / ".github" / "workflows" / "release.yml")["jobs"]["build"]["steps"]]
    assert names.index("Build the dashboard front end") < names.index("Build")


def test_web_packages_are_pinned_to_exact_versions():
    package = json.loads((REPO / "web" / "package.json").read_text(encoding="utf-8"))
    for group in ("dependencies", "devDependencies"):
        for name, version in package[group].items():
            assert re.fullmatch(r"\d+\.\d+\.\d+", version), (name, version)
    assert (REPO / "web" / "package-lock.json").is_file()


def test_a_release_runs_on_tags_alone_and_only_its_publish_job_can_prove_who_it_is():
    workflow = load(REPO / ".github" / "workflows" / "release.yml")
    assert workflow["on"] == {"push": {"tags": ["v*"]}}
    build, publish = workflow["jobs"]["build"], workflow["jobs"]["publish"]
    assert "permissions" not in build and publish["permissions"] == {"id-token": "write"}
    assert publish["environment"]["name"] == "pypi"  # the name PyPI's trusted publisher holds
    assert all("run" not in step and "checkout" not in step["uses"] for step in publish["steps"])
    assert publish["steps"][-1]["uses"].startswith("pypa/gh-action-pypi-publish@")
    assert not [step for step in steps(workflow) if "GH_TOKEN" in step.get("env", {})]


def test_a_release_checks_its_tag_and_that_the_wheel_holds_the_dashboard():
    build = load(REPO / ".github" / "workflows" / "release.yml")["jobs"]["build"]
    names = [step.get("name") for step in build["steps"]]
    assert names.index("The tag is the version") < names.index("Build") < names.index("Try it")
    tried = build["steps"][names.index("Try it")]["run"]
    assert "mulebox/dashboard/app/index.html" in tried and "--version" in tried


def test_the_readme_on_pypi_links_to_the_release_on_github():
    spec = importlib.util.spec_from_file_location("pypi_readme", REPO / "tools" / "pypi_readme.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    text = ('[Install](docs/install.md#2-install-on-the-dev-machine) ![q](docs/images/queue-dark.png) '
            '<img src="docs/images/phone-dark.png"> [web](https://example.com) [up](#install)')
    assert tool.absolute(text, "v1.1.0") == (
        "[Install](https://github.com/typerhack/mulebox/blob/v1.1.0/docs/install.md#2-install-on-the-dev-machine) "
        "![q](https://raw.githubusercontent.com/typerhack/mulebox/v1.1.0/docs/images/queue-dark.png) "
        '<img src="https://raw.githubusercontent.com/typerhack/mulebox/v1.1.0/docs/images/phone-dark.png"> '
        "[web](https://example.com) [up](#install)")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert not re.search(r"\]\((?!https?:|#)|(?:src|srcset|href)=\"(?!https?:|#)",
                         tool.absolute(readme, "v1.0.0"))
    build = load(REPO / ".github" / "workflows" / "release.yml")["jobs"]["build"]
    names = [step.get("name") for step in build["steps"]]
    assert names.index("Point the README's links at GitHub") < names.index("Build")


def test_docs_alone_run_nothing_and_code_always_runs():
    on = load(REPO / ".github" / "workflows" / "ci.yml")["on"]
    ignored = on["push"]["paths-ignore"]
    assert on["pull_request"]["paths-ignore"] == ignored
    for pattern in ignored:  # never code: no `*.md` that would reach the packaged SKILL.md
        assert "/" not in pattern or pattern.startswith("docs/"), pattern
        assert pattern.endswith((".md", ".html")) or pattern in ("LICENSE", "VERSION"), pattern
    local = yaml.safe_load((REPO / ".mulebox.yml").read_text(encoding="utf-8"))["ignore_changes"]
    assert [p.replace("**/", "") for p in ignored] == local  # mulebox check skips the same files
