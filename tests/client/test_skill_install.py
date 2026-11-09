"""`mulebox skill`: only ever against temporary folders, never a real config folder."""

import json

import pytest

from mulebox import cli
from mulebox.client import skill_install as si
from mulebox.client.contract import SCHEMA

PACKAGED = si.packaged_text()
OLD = PACKAGED.replace(f"written for contract schema {SCHEMA}", "written for contract schema 1")


@pytest.fixture
def home(tmp_path, monkeypatch):
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.delenv(si.ENV_FOLDER, raising=False)
    return folder


def folder_in(parent, name):
    path = parent / name
    path.mkdir()
    return path


def put(folder, text):
    path = si.skill_path(folder)
    path.parent.mkdir(parents=True)
    path.write_text(text)
    return path


def run(capsys, *argv):
    code = cli.main(["skill", *argv])
    return code, capsys.readouterr()


def test_the_packaged_skill_says_its_schema():
    assert si.schema_of(PACKAGED) == SCHEMA


def test_folders_found_are_every_one_that_exists(tmp_path, home):
    claude, work = folder_in(home, ".claude"), folder_in(home, ".claude-work")
    named = folder_in(tmp_path, "custom")
    assert si.config_folders({si.ENV_FOLDER: str(named)}, home) == [named, claude, work]


def test_a_folder_is_listed_once_however_it_is_reached(home):
    claude = folder_in(home, ".claude")
    assert si.config_folders({si.ENV_FOLDER: str(claude)}, home) == [claude]


def test_missing_folders_are_not_created_or_listed(tmp_path, home):
    assert si.config_folders({si.ENV_FOLDER: str(tmp_path / "gone")}, home) == []
    assert not (home / ".claude").exists()


@pytest.mark.parametrize("text,state", [
    (PACKAGED, si.CURRENT),
    (OLD, si.BEHIND),
    ("# no stamp, from before skills had one\n", si.BEHIND),
    (PACKAGED + "\nedited\n", si.DIFFERS),
    (PACKAGED.replace(f"written for contract schema {SCHEMA}",
                      f"written for contract schema {SCHEMA + 1}"), si.AHEAD),
])
def test_states(tmp_path, text, state):
    folder = folder_in(tmp_path, "c")
    put(folder, text)
    assert si.inspect(folder, PACKAGED).state == state


def test_a_link_is_never_written_through(tmp_path, capsys):
    target = folder_in(tmp_path, "checkout")
    (target / "SKILL.md").write_text("mine\n")
    folder = folder_in(tmp_path, "c")
    (folder / "skills").mkdir()
    (folder / "skills" / "mulebox").symlink_to(target)
    assert si.inspect(folder, PACKAGED).state == si.LINKED
    code, out = run(capsys, "update", "--config-dir", str(folder))
    assert code == 0 and "link" in out.out and (target / "SKILL.md").read_text() == "mine\n"


def test_install_reaches_every_folder(tmp_path, home, monkeypatch, capsys):
    claude, work = folder_in(home, ".claude"), folder_in(home, ".claude-work")
    named = folder_in(tmp_path, "custom")
    monkeypatch.setenv(si.ENV_FOLDER, str(named))
    code, out = run(capsys, "install")
    assert code == 0 and out.out.count("installed") == 3
    for folder in (claude, work, named):
        assert si.skill_path(folder).read_text() == PACKAGED


def test_install_leaves_an_existing_copy(home, capsys):
    path = put(folder_in(home, ".claude"), OLD)
    code, out = run(capsys, "install")
    assert code == 0 and "skill update" in out.out and path.read_text() == OLD


def test_update_replaces_only_what_is_there(home, capsys):
    claude, work = folder_in(home, ".claude"), folder_in(home, ".claude-work")
    path = put(claude, OLD)
    code, out = run(capsys, "update")
    assert code == 0 and "updated" in out.out and path.read_text() == PACKAGED
    assert not si.skill_path(work).exists()


def test_update_leaves_a_newer_skill_alone(tmp_path, capsys):
    folder = folder_in(tmp_path, "c")
    newer = PACKAGED.replace(f"schema {SCHEMA}", f"schema {SCHEMA + 1}")
    path = put(folder, newer)
    code, out = run(capsys, "update", "--config-dir", str(folder))
    assert code == 0 and "upgrade mulebox" in out.out and path.read_text() == newer


def test_no_temporary_file_stays_behind(tmp_path, capsys):
    folder = folder_in(tmp_path, "c")
    run(capsys, "install", "--config-dir", str(folder))
    assert [p.name for p in si.skill_path(folder).parent.iterdir()] == ["SKILL.md"]


def test_config_dir_replaces_the_search(tmp_path, home, capsys):
    claude = folder_in(home, ".claude")
    chosen = folder_in(tmp_path, "chosen")
    run(capsys, "install", "--config-dir", str(chosen))
    assert si.skill_path(chosen).exists() and not si.skill_path(claude).exists()


def test_a_config_dir_that_does_not_exist_is_an_error(tmp_path, capsys):
    code, out = run(capsys, "install", "--config-dir", str(tmp_path / "gone"))
    assert code == 2 and "no such folder" in out.err


def test_no_folder_at_all_is_an_error_for_install_not_for_status(home, capsys):
    code, out = run(capsys, "install")
    assert code == 2 and "--config-dir" in out.err
    code, out = run(capsys, "status")
    assert code == 0 and "no Claude config folder" in out.out


def test_status_changes_nothing_and_reports_schemas(home, capsys):
    claude, work = folder_in(home, ".claude"), folder_in(home, ".claude-work")
    path = put(claude, OLD)
    code, out = run(capsys, "status", "--json")
    data = json.loads(out.out)
    assert code == 0 and data["contract_schema"] == SCHEMA
    assert data["copies"] == [
        {"folder": str(claude), "state": si.BEHIND, "schema": 1},
        {"folder": str(work), "state": si.MISSING, "schema": None}]
    assert path.read_text() == OLD and not si.skill_path(work).exists()


def test_status_as_text(home, capsys):
    put(folder_in(home, ".claude"), PACKAGED)
    code, out = run(capsys, "status")
    assert code == 0 and f"contract schema {SCHEMA}" in out.out and ": current" in out.out


def test_contract_says_when_a_copy_is_out_of_date_even_with_the_same_schema(
        home, tmp_path, monkeypatch, capsys):
    claude = folder_in(home, ".claude")
    path = put(claude, PACKAGED.replace("## What to do with it", "## An older text"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MULEBOX_CONFIG", str(tmp_path / "missing.toml"))
    assert cli.main(["contract"]) == 0
    err = capsys.readouterr().err
    assert "skill is out of date" in err and str(path) in err and "mulebox skill update" in err
    assert run(capsys, "update")[0] == 0
    assert cli.main(["contract"]) == 0
    assert "out of date" not in capsys.readouterr().err


def test_contract_is_quiet_with_no_copy_or_a_current_one(home, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MULEBOX_CONFIG", str(tmp_path / "missing.toml"))
    assert cli.main(["contract"]) == 0
    assert "skill" not in capsys.readouterr().err
    put(folder_in(home, ".claude"), PACKAGED)
    assert cli.main(["contract"]) == 0
    assert "skill" not in capsys.readouterr().err


def test_the_skill_tells_the_agent_to_update_itself():
    assert "run `mulebox skill update`" in PACKAGED and "read the\nSKILL.md" in PACKAGED


def test_setup_refresh_updates_old_copies_and_leaves_the_rest(home):
    old = put(folder_in(home, ".claude"), OLD)
    folder_in(home, ".claude-work")  # no copy there: none is added
    lines = si.refresh_here()
    assert old.read_text() == PACKAGED and len(lines) == 1 and "updated" in lines[0]
    assert not si.skill_path(home / ".claude-work").exists()
    assert si.refresh_here() == []


def test_the_state_a_submit_reports(home):
    assert si.state_here() == "none"
    claude = folder_in(home, ".claude")
    put(claude, PACKAGED)
    assert si.state_here() == "current"
    put(folder_in(home, ".claude-work"), OLD)
    assert si.state_here() == "out_of_date"
