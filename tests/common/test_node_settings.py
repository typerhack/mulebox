"""The rules of a node's editable settings (common/node_settings.py) and node.toml's reading."""

import pytest

from mulebox.common import node_settings as ns
from mulebox.common.config import ConfigError, load_node_config

GIB = 1 << 30  # what machines have; the budget and the text are decimal


@pytest.mark.parametrize("cores, memory_gb, slots", [
    (8, 16, 2), (16, 32, 4), (4, 8, 1), (2, 4, 1), (64, 16, 2), (32, 256, 8), (512, 4096, 64)])
def test_the_suggestion_is_about_4_cores_and_6_gb_a_job(cores, memory_gb, slots):
    tip = ns.suggest_slots(cores, memory_gb * GIB)
    assert tip["slots"] == slots and f"{cores} cores" in tip["reason"]


def test_the_reason_counts_in_decimal_gb_like_every_size_shown():
    assert ns.suggest_slots(8, 16 * GIB)["reason"] == (
        "8 cores and 17.2 GB of memory, at about 4 cores and 6 GB a job")
    assert ns.suggest_slots(16, 32 * GIB)["reason"].startswith("16 cores and 34.4 GB of memory")
    assert ns.suggest_slots(4, 11_900_000_000)["slots"] == 1  # under 2 x 6 decimal GB
    assert ns.suggest_slots(4, 12_000_000_000)["slots"] == 1  # cores hold it at 1
    assert ns.suggest_slots(8, 12_000_000_000)["slots"] == 2


def test_no_suggestion_without_readings():
    assert ns.suggest_slots(None, 16 * GIB) is None and ns.suggest_slots(8, None) is None


def test_priority_ranks_and_an_unknown_one_counts_as_normal():
    assert ns.rank("preferred") > ns.rank("normal") > ns.rank("fallback")
    assert ns.rank(None) == ns.rank("bogus") == ns.rank("normal")


def test_only_slots_and_priority_can_be_changed_from_afar():
    assert ns.checked({"slots": 3, "priority": "fallback"}) == {"slots": 3, "priority": "fallback"}
    with pytest.raises(ValueError, match="cannot be changed from afar"):
        ns.checked({"job_env": {"PATH": "/tmp"}})
    with pytest.raises(ValueError):
        ns.checked([1])


def write(tmp_path, extra):
    roots = "\n".join(f'{key} = "{tmp_path}/{key}"' for key in ("jobs", "cache", "staging", "runners"))
    path = tmp_path / "node.toml"
    path.write_text(f'name = "build-1"\nroles = ["coordinator", "worker"]\n{extra}\n[roots]\n{roots}\n')
    return path


def test_node_toml_reads_priority_and_keeps_slots_in_range(tmp_path):
    node = load_node_config(write(tmp_path, ""))
    assert node.priority == "normal" and node.slots == 1
    assert load_node_config(write(tmp_path, 'priority = "fallback"\nslots = 3')).priority == "fallback"
    with pytest.raises(ConfigError, match="priority"):
        load_node_config(write(tmp_path, 'priority = "first"'))
    with pytest.raises(ConfigError, match="slots"):
        load_node_config(write(tmp_path, "slots = 0"))
