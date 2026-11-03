from pathlib import Path

import pytest

from mulebox import cli, get_version

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_version_file():
    assert get_version() == (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_version_command_prints_version(capsys):
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == get_version()


def test_version_flag_prints_name_and_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"mulebox {get_version()}"


def test_no_command_prints_help(capsys):
    assert cli.main([]) == 0
    assert "usage: mulebox" in capsys.readouterr().out
