"""The `mulebox runner` CLI: parsing, token on stdin, exit codes."""

import io

import pytest

from mulebox import cli
from mulebox.runners import commands_manage, github, manage

from .conftest import TOKEN

REPO = "example-org/example-app"


@pytest.fixture
def node_toml(tmp_path, paths):
    path = tmp_path / "node.toml"
    roots = "\n".join(f'{k} = "{getattr(paths, k)}"' for k in ("jobs", "cache", "staging",
                                                                "runners"))
    path.write_text(f'name = "build-1"\nroles = ["coordinator", "worker"]\n[roots]\n{roots}\n')
    return path


def test_add_reads_the_token_from_stdin(monkeypatch, node_toml):
    seen = {}
    monkeypatch.setattr("sys.stdin", io.StringIO(TOKEN + "\n"))
    monkeypatch.setattr(manage, "add", lambda m, repo, token, **kw: seen.update(
        repo=repo, token=token, node=m.node, **kw))
    code = cli.main(["runner", "add", "--repo", REPO, "--labels", "mulebox,gpu",
                     "--config", str(node_toml)])
    assert code == 0
    assert seen == {"repo": REPO, "token": TOKEN, "node": "build-1",
                    "name": "build-1-example-app", "labels": ("mulebox", "gpu")}


def test_errors_are_redacted_and_mapped(monkeypatch, node_toml, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(TOKEN + "\n"))

    def fail(m, repo, token, **kw):
        raise manage.RunnerError(f"failed with {token}")

    monkeypatch.setattr(manage, "add", fail)
    code = cli.main(["runner", "add", "--repo", REPO, "--config", str(node_toml)])
    assert code == 1
    err = capsys.readouterr().err
    assert TOKEN not in err and "[redacted]" in err


def test_empty_stdin_is_a_usage_error(monkeypatch, node_toml):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli.main(["runner", "add", "--repo", REPO, "--config", str(node_toml)]) == 2


def test_bad_repo_is_a_usage_error(monkeypatch, node_toml):
    monkeypatch.setattr("sys.stdin", io.StringIO(TOKEN + "\n"))
    assert cli.main(["runner", "add", "--repo", "a/b/c", "--config", str(node_toml)]) == 2


def test_remove_needs_a_name_or_repo(node_toml):
    assert cli.main(["runner", "remove", "--config", str(node_toml)]) == 2


def test_list_prints_a_table(monkeypatch, node_toml, capsys):
    rows = [manage.RunnerInfo("build-1-example-app", REPO, "active", False)]
    monkeypatch.setattr(manage, "list_runners", lambda m: rows)
    assert cli.main(["runner", "list", "--config", str(node_toml)]) == 0
    assert "build-1-example-app" in capsys.readouterr().out


def test_register_maps_gh_failure_to_exit_4(monkeypatch, tmp_path):
    client = tmp_path / "client.toml"
    client.write_text('coordinator = "build-1"\n')
    monkeypatch.setenv("MULEBOX_CONFIG", str(client))

    def fail(config, repo, **kw):
        raise github.GitHubError("gh could not get a token")

    monkeypatch.setattr(github, "register", fail)
    assert cli.main(["runner", "register", "--repo", REPO]) == 4


def test_parser_has_all_actions():
    parser = cli.build_parser()
    for action in ("add", "list", "remove", "register", "unregister"):
        with pytest.raises(SystemExit) as info:
            parser.parse_args(["runner", action, "--help"])
        assert info.value.code == 0
    assert commands_manage.EXIT_FAILED == 1
