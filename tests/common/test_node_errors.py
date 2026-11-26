"""A node's own commands tell their errors as every command does: code, message, fix."""

from mulebox import cli


def test_a_node_command_with_a_broken_node_toml_says_node_config(tmp_path, capsys):
    bad = tmp_path / "node.toml"
    bad.write_text("this is = = not toml\n")
    assert cli.main(["toolchain", "list", "--config", str(bad)]) == 2
    err = capsys.readouterr().err.splitlines()
    assert err[0].startswith("mulebox: error [node.config]: ")
    assert err[1].startswith("mulebox: fix: correct the key the message names in node.toml")


def test_the_coordinators_rpc_with_no_node_toml_says_node_config(tmp_path, capsys):
    assert cli.main(["rpc", "--node-config", str(tmp_path / "none.toml")]) == 2
    assert "mulebox: error [node.config]: " in capsys.readouterr().err
