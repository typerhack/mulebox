"""Settings from afar written into node.toml (worker/node_file.py), and read back live
(worker/live_config.py)."""

import os

import pytest

from mulebox.common.config import load_node_config
from mulebox.worker import live_config, node_file

NODE_TOML = """# the node's own comments stay
name = "build-1"
roles = ["coordinator", "worker"]

# Jobs at once.
slots = 2  # the default

capabilities = ["docker"]

[roots]
jobs = "{base}/jobs"
cache = "{base}/cache"
staging = "{base}/staging"
runners = "{base}/runners"
"""


@pytest.fixture
def toml(tmp_path):
    folder = tmp_path / "config"
    folder.mkdir()
    path = folder / "node.toml"
    path.write_text(NODE_TOML.format(base=tmp_path))
    path.chmod(0o600)
    return path


def test_slots_is_replaced_and_priority_added_before_the_first_table(toml):
    config = node_file.apply(toml, {"slots": 3, "priority": "preferred"})
    assert config.slots == 3 and config.priority == "preferred"
    text = toml.read_text()
    assert "slots = 3  # the default\n" in text
    assert "# the node's own comments stay" in text and "# Jobs at once." in text
    assert text.index('priority = "preferred"') < text.index("[roots]")
    assert load_node_config(toml) == config
    assert toml.stat().st_mode & 0o777 == 0o600  # the file keeps its mode


def test_a_line_that_is_missing_is_added_and_a_comment_is_not_taken_for_it():
    text = '# slots = 9\nname = "build-1"\n[roots]\njobs = "/x"\n'
    out = node_file.with_settings(text, {"slots": 4})
    assert out.startswith('# slots = 9\nname = "build-1"\nslots = 4\n\n[roots]')


def test_a_table_value_of_the_same_name_is_left_alone():
    text = 'name = "b"\nslots = 1\n[dashboard]\npriority = "x"\n'
    out = node_file.with_settings(text, {"priority": "fallback"})
    assert out == 'name = "b"\nslots = 1\npriority = "fallback"\n\n[dashboard]\npriority = "x"\n'


def test_a_bad_value_or_a_file_that_would_not_read_changes_nothing(toml):
    before = toml.read_text()
    with pytest.raises(node_file.NodeFileError, match="from 1 to 64"):
        node_file.apply(toml, {"slots": 0})
    assert toml.read_text() == before
    toml.write_text(before.replace("[roots]", "[roots]\nbogus = 1"))
    broken = toml.read_text()
    with pytest.raises(node_file.NodeFileError, match="would not read"):
        node_file.apply(toml, {"slots": 3})
    assert toml.read_text() == broken


def test_a_symlinked_node_toml_is_refused(toml, tmp_path):
    real = tmp_path / "config" / "real.toml"
    os.rename(toml, real)
    toml.symlink_to(real)
    with pytest.raises(node_file.NodeFileError):
        node_file.apply(toml, {"slots": 3})
    assert "slots = 2" in real.read_text()


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def test_a_change_from_afar_is_written_once_and_a_failure_is_not_retried(toml, tmp_path):
    node, clock = load_node_config(toml), Clock()
    live = live_config.LiveConfig(toml, clock)
    node = live.follow(node, {"node_settings": {"slots": 4}, "node_settings_at": 5.0})
    assert node.slots == 4 and "slots = 4" in toml.read_text()
    assert live_config.report(node, live.error) == {"slots": 4, "priority": "normal"}
    clock.now = 10.0
    assert live.check(node) is node  # its own write is not taken for a hand edit
    real = tmp_path / "real.toml"
    os.rename(toml, real)
    toml.symlink_to(real)  # refused (node_file.py)
    asked = {"node_settings": {"slots": 5}, "node_settings_at": 6.0}
    assert live.follow(node, asked) is node and live.error
    assert live_config.report(node, live.error)["error"] == live.error
    live.error = "kept"
    assert live.follow(node, asked) is node and live.error == "kept"  # not tried again
    toml.unlink()
    os.rename(real, toml)
    node = live.follow(node, {"node_settings": {"slots": 5}, "node_settings_at": 7.0})
    assert node.slots == 5 and live.error is None


def test_a_hand_edit_applies_live_and_a_broken_one_keeps_the_old_values(toml, caplog):
    node, clock = load_node_config(toml), Clock()
    live = live_config.LiveConfig(toml, clock)
    text = toml.read_text()
    toml.write_text(text.replace("slots = 2  # the default", 'slots = 3\npriority = "fallback"')
                    .replace('capabilities = ["docker"]', 'capabilities = ["docker", "playwright"]'))
    assert live.check(node) is node  # not yet: it looks every 2 s
    clock.now = live_config.CHECK_EVERY_S
    node = live.check(node)
    assert (node.slots, node.priority, node.capabilities) == (3, "fallback", ("docker", "playwright"))
    toml.write_text(text.replace("[roots]", "retention = 3\n[roots]"))
    clock.now += live_config.CHECK_EVERY_S
    assert live.check(node).slots == 3
    toml.write_text(text.replace('roles = ["coordinator", "worker"]', 'roles = ["worker"]\n'
                                 'coordinator = "build-0"').replace("slots = 2", "slots = 1"))
    clock.now += live_config.CHECK_EVERY_S
    node = live.check(node)
    assert node.slots == 1 and node.roles == ("coordinator", "worker")  # roles need a restart
    assert "restart" in caplog.text


def test_a_trailing_comment_on_the_line_is_kept():
    text = 'slots = 2 # leave room for my own work\npriority = "normal"\t# "quoted # inside"\n'
    out = node_file.with_settings(text, {"slots": 3, "priority": "fallback"})
    assert out == 'slots = 3 # leave room for my own work\npriority = "fallback"\t# "quoted # inside"\n'
    hashed = "priority = 'a#b'  # note\n"
    assert node_file.with_settings(hashed, {"priority": "preferred"}) == 'priority = "preferred"  # note\n'


@pytest.mark.parametrize("key", ['"slots"', "'slots'", '"\\u0073lots"'])
def test_a_quoted_key_is_taken_for_its_setting(toml, key):
    toml.write_text(toml.read_text().replace("slots = 2", f"{key} = 2"))
    config = node_file.apply(toml, {"slots": 3})
    assert config.slots == 3
    assert f"{key} = 3  # the default\n" in toml.read_text()


def test_a_quoted_key_of_another_name_is_left_alone():
    text = '"slots.x" = 1\n"slot" = 2\n'
    assert node_file.with_settings(text, {"slots": 3}) == text + "slots = 3\n"


def test_a_node_toml_too_big_to_read_whole_is_refused_and_not_cut(toml):
    big = toml.read_text() + "# " + "x" * (node_file.MAX_BYTES + 10) + "\n"
    toml.write_text(big)
    with pytest.raises(node_file.NodeFileError, match="too big"):
        node_file.apply(toml, {"slots": 3})
    assert toml.read_text() == big
