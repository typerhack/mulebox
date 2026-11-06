"""What a machine offers is found out, and a list a person wrote is left alone."""

from mulebox.worker import offers


def answers(*fails):
    return lambda argv: " ".join(argv[1:]) not in fails and argv[0] != "absent"


def test_docker_states():
    assert offers.docker_state(answers()) == "ok"
    assert offers.docker_state(answers("info")) == "no-access"
    assert offers.docker_state(answers("compose version")) == "missing"
    assert offers.docker_state(answers("--version")) == "missing"


def test_an_empty_list_is_filled(tmp_path):
    path = tmp_path / "node.toml"
    path.write_text('name = "build-1"\ncapabilities = []\n\n[roots]\n')
    assert offers.fill_capabilities(path, ["docker"]) == ["docker"]
    assert 'capabilities = ["docker"]\n\n[roots]' in path.read_text()


def test_a_written_list_stays(tmp_path):
    path = tmp_path / "node.toml"
    path.write_text('capabilities = ["playwright"]\n')
    assert offers.fill_capabilities(path, ["docker"]) == []
    assert path.read_text() == 'capabilities = ["playwright"]\n'


def test_nothing_found_changes_nothing(tmp_path):
    path = tmp_path / "node.toml"
    path.write_text("capabilities = []\n")
    assert offers.fill_capabilities(path, []) == []
