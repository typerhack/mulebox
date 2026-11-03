"""Worker CLI: `toolchain list|install` and `worker serve` argument handling."""

import pytest

from mulebox import cli
from mulebox.worker import commands


def _node_toml(tmp_path, roots_config, roles='["worker"]', extra='coordinator = "build-1"'):
    lines = ['name = "build-2"', f"roles = {roles}", extra, "[roots]"]
    lines += [f'{key} = "{value}"' for key, value in roots_config.items()]
    path = tmp_path / "node.toml"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_toolchain_list(tmp_path, roots_config, capsys):
    bin_dir = tmp_path / "cache" / "toolchains" / "node" / "22.22.3" / "bin"
    bin_dir.mkdir(parents=True)
    config = _node_toml(tmp_path, roots_config)
    assert cli.main(["toolchain", "list", "--config", str(config)]) == 0
    assert capsys.readouterr().out == "node\t22.22.3\n"


def test_toolchain_install_error_is_reported(tmp_path, roots_config, capsys):
    config = _node_toml(tmp_path, roots_config)
    assert cli.main(["toolchain", "install", "ruby", "3.3.0", "--config", str(config)]) == 2
    assert "unknown toolchain" in capsys.readouterr().err


def test_serve_refuses_node_without_worker_role(tmp_path, roots_config, capsys):
    config = _node_toml(tmp_path, roots_config, roles='["coordinator"]', extra="")
    assert cli.main(["worker", "serve", "--config", str(config)]) == 2
    assert "worker" in capsys.readouterr().err


def test_serve_bad_config(tmp_path, capsys):
    assert cli.main(["worker", "serve", "--config", str(tmp_path / "missing.toml")]) == 2


def test_ssh_link_for_remote_coordinator(tmp_path, roots_config):
    from mulebox.common.config import load_node_config
    from mulebox.worker.link import SSHLink
    from mulebox.worker.paths import NodePaths

    node = load_node_config(_node_toml(tmp_path, roots_config))
    link = commands.open_link(node, NodePaths.from_config(node.roots))
    assert isinstance(link, SSHLink) and link.target == "build-1"
    assert link.remote_bin == ".mulebox/bin/mulebox"


def test_subcommand_required(capsys):
    with pytest.raises(SystemExit):
        cli.main(["toolchain"])
