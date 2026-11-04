"""The agent skill: valid to load, short, and leaning on the contract, not copying it."""

import re
from pathlib import Path

import yaml

from mulebox.cli import build_parser
from mulebox.client import contract, skill_install

SKILL = Path(__file__).resolve().parents[1] / "skills" / "mulebox" / "SKILL.md"
MAX_DESCRIPTION = 1024


def parts():
    text = SKILL.read_text(encoding="utf-8")
    match = re.fullmatch(r"---\n(.*?)\n---\n(.*)", text, re.S)
    assert match, "SKILL.md needs a frontmatter block"
    return yaml.safe_load(match[1]), match[2]


def test_frontmatter_is_what_a_skill_loader_needs():
    meta, _ = parts()
    assert meta["name"] == SKILL.parent.name
    assert 0 < len(meta["description"]) <= MAX_DESCRIPTION
    assert "mulebox.yml" in meta["description"]  # what makes it trigger in a project


def test_the_schema_it_was_written_for_is_the_contract_schema():
    """Raising contract.SCHEMA means revisiting the skill, and stating the new number in it."""
    assert skill_install.schema_of(SKILL.read_text(encoding="utf-8")) == contract.SCHEMA


def test_the_repository_path_and_the_packaged_skill_are_one_file():
    assert SKILL.is_symlink()
    assert SKILL.read_text(encoding="utf-8") == skill_install.packaged_text()


def test_it_tells_the_agent_to_report_a_stale_skill_and_not_to_update_it():
    body = parts()[1]
    assert "mulebox skill update" in body
    assert "Never update this skill\nyourself" in body


def test_it_teaches_detached_jobs_and_following_them():
    body = parts()[1]
    assert "mulebox check --detach" in body and "mulebox events --job" in body
    assert "Monitor tool" in body


def test_it_sends_agents_to_the_contract():
    assert "mulebox contract" in parts()[1]


def test_it_does_not_copy_what_the_contract_generates():
    body = parts()[1]
    assert "never" in body.lower()  # the fallback rule stays, on purpose
    for code, _, _ in contract.EXIT_CODES:
        if code not in (2, 3):  # 3 means stop, so it stays; "section 2" is not a code
            assert not re.search(rf"\b{code}\b", body)


def test_every_mulebox_command_it_names_exists():
    body = parts()[1]
    known = set(build_parser()._subparsers._group_actions[0].choices)
    named = set(re.findall(r"`mulebox ([a-z]+)", body)) | set(
        re.findall(r"^ {4}mulebox ([a-z]+)", body, re.M))
    assert {"doctor", "events", "status", "wait", "skill"} <= named
    assert named and named <= known


def test_no_personal_paths_or_hosts():
    text = SKILL.read_text(encoding="utf-8")
    assert not re.search(r"/Users/|/home/|\b\d{1,3}(\.\d{1,3}){3}\b", text)
