"""The agent skill: valid to load, short, and leaning on the contract, not copying it."""

import re
from pathlib import Path

import yaml

from mulebox.cli import build_parser
from mulebox.client import contract

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
    assert named and named <= known


def test_no_personal_paths_or_hosts():
    text = SKILL.read_text(encoding="utf-8")
    assert not re.search(r"/Users/|/home/|\b\d{1,3}(\.\d{1,3}){3}\b", text)
