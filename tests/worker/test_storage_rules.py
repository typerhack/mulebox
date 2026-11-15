"""What the sweep does with each branch folder (worker/storage_rules.py), and the storage
settings it follows (common/storage_policy.py)."""

import pytest

from mulebox.common.storage_policy import StoragePolicy, check, read
from mulebox.worker.storage_rules import (DAY, KEPT, LATEST, REMOVE, RUNNING, STAYS, Folder,
                                          plan)

NOW = 1_000 * DAY
GB = 10**9


def folder(project, name, days_ago, size=GB):
    return Folder(project, name, size, None if days_ago is None else NOW - days_ago * DAY)


def fates(result):
    return {(f.project, f.folder): f.fate for f in result.folders}


def test_old_folders_go_and_the_latest_stays_however_old():
    result = plan([folder("miu", "main", 30), folder("miu", "pr-1", 20), folder("miu", "pr-2", 2)],
                  StoragePolicy(), NOW, set(), set())
    assert fates(result) == {("miu", "pr-2"): LATEST, ("miu", "pr-1"): REMOVE,
                             ("miu", "main"): REMOVE}
    alone = plan([folder("old", "main", 400)], StoragePolicy(), NOW, set(), set())
    assert fates(alone) == {("old", "main"): LATEST}


def test_a_folder_used_lately_says_when_it_would_go():
    result = plan([folder("miu", "a", 1), folder("miu", "b", 5)], StoragePolicy(), NOW,
                  set(), set())
    b = next(f for f in result.folders if f.folder == "b")
    assert b.fate == STAYS and b.removed_in == pytest.approx(2.0)


def test_running_and_kept_folders_never_go():
    folders = [folder("miu", "a", 1), folder("miu", "b", 30), folder("miu", "c", 30),
               folder("clinic", "x", 1), folder("clinic", "y", 30)]
    result = plan(folders, StoragePolicy(), NOW, {("miu", "c"), ("clinic", None)}, {("miu", "b")})
    assert fates(result) == {("miu", "a"): LATEST, ("miu", "b"): RUNNING, ("miu", "c"): KEPT,
                             ("clinic", "x"): KEPT, ("clinic", "y"): KEPT}


def test_without_keep_latest_an_old_latest_goes_too():
    result = plan([folder("miu", "a", 30)], StoragePolicy(keep_latest=False), NOW, set(), set())
    assert fates(result) == {("miu", "a"): REMOVE}


def test_a_folder_with_no_known_job_counts_as_long_ago():
    result = plan([folder("miu", "a", 1), folder("miu", "b", None)], StoragePolicy(), NOW,
                  set(), set())
    assert fates(result)[("miu", "b")] == REMOVE


def test_an_idle_project_gets_a_suggestion_not_a_removal():
    result = plan([folder("miu", "a", 20, size=2 * GB), folder("miu", "b", 30),
                   folder("clinic", "x", 3)], StoragePolicy(), NOW, set(), set())
    assert fates(result)[("miu", "a")] == LATEST
    assert result.idle == [{"project": "miu", "days": 20, "size": 2 * GB, "kept": False}]


def test_short_lists_what_could_go_next_oldest_first_until_the_gap_is_covered():
    folders = [folder("miu", "a", 1, 5 * GB), folder("miu", "b", 3, 4 * GB),
               folder("clinic", "x", 10, 3 * GB), folder("clinic", "old", 30, 2 * GB)]
    result = plan(folders, StoragePolicy(), NOW, set(), set(), free=10 * GB, reserve=16 * GB)
    # the planned removal frees 2 GB: 4 GB short; the clinic latest (3) and miu's b (4) cover it
    assert result.short["need"] == 4 * GB
    assert [(f["project"], f["folder"]) for f in result.short["folders"]] == [
        ("clinic", "x"), ("miu", "b")]
    assert result.short["could_free"] == 7 * GB
    enough = plan(folders, StoragePolicy(), NOW, set(), set(), free=20 * GB, reserve=16 * GB)
    assert enough.short is None


def test_the_reserve_is_a_share_or_a_size():
    assert StoragePolicy().reserve(490 * GB) == 49 * GB
    assert StoragePolicy(keep_free="20%").reserve(500 * GB) == 100 * GB
    assert StoragePolicy(keep_free="50GB").reserve(500 * GB) == 50 * GB
    assert StoragePolicy(keep_free="1.5TB").reserve(4000 * GB) == 1500 * GB


@pytest.mark.parametrize("name, value", [
    ("keep_free", "95%"), ("keep_free", "0%"), ("keep_free", "lots"), ("keep_free", 10),
    ("keep_free", "0GB"), ("unused_days", 0), ("unused_days", 366), ("unused_days", True),
    ("idle_days", "14"), ("keep_latest", "yes")])
def test_bad_settings_are_refused_with_the_name(name, value):
    with pytest.raises(ValueError, match=name):
        check(name, value)


def test_settings_read_with_defaults_and_spelling_kept_plain():
    policy = read({"keep_free": " 50 gb ", "unused_days": 3})
    assert policy == StoragePolicy(keep_free="50GB", unused_days=3)
    assert read({}).report() == {"keep_free": "10%", "unused_days": 7, "keep_latest": True,
                                 "idle_days": 14, "auto_clean": True, "docker_clean": True,
                                 "warn_size": "20GB", "max_size": "OFF", "slim_hours": 12}
