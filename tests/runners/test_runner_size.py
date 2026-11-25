"""A runner's size (runners/runner_size.py): asked, kept, read back and sent on."""

import pytest

from mulebox.runners import layout, runner_size
from mulebox.runners.names import RunnerUsageError


def test_asked_and_turned_into_flags():
    assert runner_size.asked(None, None) is None
    size = runner_size.asked(6, "8GB")
    assert size == {"cores": 6.0, "memory": 8 * 10**9}
    assert runner_size.argv(size) == ["--cores", "6", "--memory", "8000MB"]
    assert runner_size.asked(6, "8000MB") == size
    with pytest.raises(RunnerUsageError, match="--memory"):
        runner_size.asked(None, "lots")


def test_kept_in_the_runners_file_beside_what_was_there(paths):
    folder = paths.runners / "build-1-app"
    folder.mkdir(parents=True)
    layout.write_meta(paths, folder, {"repo": "alice/example-app"})
    runner_size.store(paths, "build-1-app", {"cores": 4.0})
    assert runner_size.of(folder) == {"cores": 4.0}
    assert layout.read_meta(folder)["repo"] == "alice/example-app"
    runner_size.store(paths, "build-1-app", None)
    assert runner_size.of(folder) is None and layout.read_meta(folder) == {"repo": "alice/example-app"}
    with pytest.raises(RunnerUsageError, match="no runner named"):
        runner_size.store(paths, "nobody", {"cores": 1.0})
