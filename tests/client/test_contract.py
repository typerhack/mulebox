"""`mulebox contract`: the facts, and tests that stop it drifting from the real tool."""

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from mulebox.cli import build_parser, main
from mulebox.client import contract
from mulebox.client.excludes import BUILTIN_EXCLUDES
from mulebox.common.config import ProjectConfig
from mulebox.common.config_jobs import JobOptions
from mulebox.version import get_version

AGENTS_DOC = Path(__file__).resolve().parents[2] / "docs" / "agents.md"
CONFIG = ProjectConfig(project="example-app", jobs={"check": "pnpm check", "test": "pnpm test"},
                       toolchain={"node": "22.22.3"}, setup="pnpm install", timeout_min=30,
                       exclude=("reports/",), env={"API_KEY": "must-not-appear"})
FILLED = {"<job-id>": "x", "<text>": "x"}
YML = "project: example-app\ntimeout_min: 30\njobs:\n  check: pnpm check\n  test: pnpm test\n"


def run(capsys, *argv):
    code = main(["contract", *argv])
    return code, capsys.readouterr()


def test_the_text_prints_the_schema_an_agent_compares_with_its_skill():
    assert f"schema {contract.SCHEMA}" in contract.render(contract.build(None, "1")).splitlines()[0]


def test_project_facts_come_from_the_config():
    terms = contract.build(CONFIG, "1.2.3")
    assert terms["schema"] == contract.SCHEMA and terms["mulebox_version"] == "1.2.3"
    assert terms["project"]["jobs"] == CONFIG.jobs and terms["project"]["full_gate"] == "check"
    assert terms["project"]["setup"] == "pnpm install"


def test_services_is_gone_and_compose_shows_what_it_implies():
    config = ProjectConfig(project="example-app", jobs={"check": "x"}, needs=("node",),
                           compose=("docker-compose.yml",))
    project = contract.build(config, "1")["project"]
    assert "services" not in project
    assert project["compose"] == ["docker-compose.yml"]
    assert project["needs"] == ["node", "docker", "compose-v1"]


def test_compose_rules_show_only_for_a_compose_project():
    plain = contract.build(CONFIG, "1")
    assert plain["compose"] == [] and "Containers:" not in contract.render(plain)
    config = ProjectConfig(project="example-app", jobs={"check": "x"},
                           compose=("docker-compose.yml",))
    terms = contract.build(config, "1")
    text = contract.render(terms)
    assert "Containers:" in text and "exec -T" in text and "MULEBOX_PORT_" in text
    assert "Compose files: docker-compose.yml" in text and "with: docker" in text


def test_project_env_is_never_shown():
    terms = contract.build(CONFIG, "1.2.3")
    assert "must-not-appear" not in json.dumps(terms)
    assert "must-not-appear" not in contract.render(terms)


def test_never_uploaded_is_the_real_list_plus_the_project_excludes():
    assert contract.build(CONFIG, "1")["never_uploaded"] == [*BUILTIN_EXCLUDES, "reports/"]


def test_every_command_in_the_contract_exists_in_the_cli():
    parser = build_parser()
    for command in contract.COMMANDS.values():
        words = [FILLED.get(w, w) for w in command.split()[1:]]
        given = [w for w in words if w != "--" and not w.startswith("<")]
        assert parser.parse_args(given).command == given[0]


def test_exit_codes_match_the_table_in_the_agent_docs():
    documented = {int(n) for n in re.findall(r"^\| (\d+) \|", AGENTS_DOC.read_text(), re.M)}
    assert documented == {code for code, _, _ in contract.EXIT_CODES}


def test_the_rule_that_matters_most_is_there():
    assert "never run heavy commands locally" in contract.RULES[0]


def test_cli_inside_a_project_with_no_client_config(tmp_path, monkeypatch, capsys):
    """No client config and no network: the contract must still answer."""
    (tmp_path / ".mulebox.yml").write_text(YML)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MULEBOX_CONFIG", str(tmp_path / "missing.toml"))
    code, out = run(capsys, "--json")
    terms = json.loads(out.out)
    assert code == 0 and terms["project"]["name"] == "example-app"
    assert terms["mulebox_version"] == get_version()


def test_cli_text_lists_the_jobs(tmp_path, monkeypatch, capsys):
    (tmp_path / ".mulebox.yml").write_text(YML)
    monkeypatch.chdir(tmp_path)
    code, out = run(capsys)
    assert code == 0 and "- mulebox check test: pnpm test" in out.out
    assert "- mulebox check: pnpm check" in out.out and "check check" not in out.out


def test_cli_outside_a_project_says_so_and_still_gives_the_rules(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, out = run(capsys)
    assert code == 0 and "not set up for mulebox" in out.out and "Rules:" in out.out
    code, out = run(capsys, "--json")
    assert code == 0 and json.loads(out.out)["project"] is None


@pytest.mark.parametrize("text", ["project: [", "project: x\n", "jobs:\n  check: a\n"])
def test_cli_broken_config_is_an_error_not_an_empty_contract(tmp_path, monkeypatch, capsys, text):
    (tmp_path / ".mulebox.yml").write_text(text)
    monkeypatch.chdir(tmp_path)
    code, out = run(capsys)
    assert code == 2 and out.out == "" and ".mulebox.yml" in out.err


@pytest.mark.parametrize("command", [["contract"], ["check"], ["run", "--", "true"]])
def test_a_later_env_entry_exits_2_with_nothing_sent(command, tmp_path, monkeypatch, capsys):
    (tmp_path / ".mulebox.yml").write_text(
        "project: example-app\njobs:\n  check: x\nenv:\n  URL: ${HOST}\n  HOST: db\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MULEBOX_CONFIG", str(tmp_path / "none.toml"))
    assert main(command) == 2
    assert "move HOST above URL" in capsys.readouterr().err


def test_the_database_rule_is_about_shared_databases():
    rule = next(r for r in contract.RULES if "database" in r)
    assert "${MULEBOX_JOB_SLUG}" in rule and "shares" in rule and "compose service" in rule


def test_git_says_a_job_has_no_history():
    assert any("no git history" in line for line in contract.GIT)


def test_job_settings_are_in_the_contract(tmp_path):
    project = replace(CONFIG, compose=("docker-compose.yml",), setup="pnpm install",
                      job_options={"lint": JobOptions(setup="", compose=False, ports=("vite",))},
                      jobs={**CONFIG.jobs, "lint": "pnpm lint"})
    terms = contract.build(project, "1")
    assert terms["project"]["job_settings"] == {
        "lint": {"setup": None, "compose": False, "ports": ["MULEBOX_PORT_VITE"]}}
    assert ("mulebox check lint: pnpm lint (setup: none, no containers, port $MULEBOX_PORT_VITE)"
            in contract.render(terms))
