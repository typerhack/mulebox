"""The cleanup's newer rules: gone branches, the size limit, the switch, Run now, and Docker
(worker/storage_rules.py, storage_sweep.py, docker_prune.py, image_use.py)."""

import subprocess
from dataclasses import replace

from mulebox.common.storage_policy import StoragePolicy
from mulebox.worker import docker_prune, image_use, storage_rules
from mulebox.worker.docker import Docker, DockerError
from mulebox.worker.storage_rules import Folder

from .test_storage_sweep import DAY, no_settle, send, worker  # noqa: F401

NOW = 1_000_000.0


def folders():
    return [Folder("app", "new", 10, NOW - 1 * DAY), Folder("app", "mid", 20, NOW - 2 * DAY),
            Folder("app", "old", 30, NOW - 3 * DAY)]


def test_a_gone_branch_goes_and_the_latest_mark_moves_to_a_live_one():
    plan = storage_rules.plan(folders(), StoragePolicy(), NOW, set(), set(),
                              gone={("app", "new")})
    fates = {f.folder: (f.fate, f.why) for f in plan.folders}
    assert fates["new"] == ("remove", "gone") and fates["mid"] == ("latest", None)
    assert fates["old"][0] == "stays"


def test_past_the_size_limit_the_oldest_that_may_go_goes():
    plan = storage_rules.plan(folders(), StoragePolicy(), NOW, set(), set())
    storage_rules.trim(plan, held=100, limit=75)
    assert [f.folder for f in plan.to_remove] == ["old"] and plan.to_remove[0].why == "size"
    storage_rules.trim(plan, held=100, limit=10)  # the latest never goes this way
    assert plan.over == 100 - 30 - 20 - 10 and {f.folder for f in plan.to_remove} == {"old", "mid"}


def test_with_the_switch_off_nothing_goes_until_asked(worker, send):  # noqa: F811
    send("main", 1)
    old = send("pr/1", 20)
    agent = worker(auto_clean=False)
    agent._sweep("hourly")
    report = agent._storage_fields()["storage"]
    assert old.is_dir() and report["sweep"]["would_remove"] == 1 and report["sweep"]["count"] == 0
    code, said = agent._sweep_order({"action": "sweep"})
    assert code == 0 and not old.exists() and "removed 1 branch folder" in said
    assert agent._store()["report"]["sweep"]["trigger"] == "now"


def test_a_folder_whose_branch_is_gone_goes_at_once(worker, send):  # noqa: F811
    send("main", 1)
    done = send("feature/a", 0)
    agent = worker()
    agent._take_replies({"storage_gone": {"example-app": ["feature/a"]}})
    agent._sweep("hourly")
    assert not done.exists()
    assert agent._store()["report"]["sweep"]["removed"][0]["why"] == "gone"


class FakeEngine(Docker):
    def __init__(self, in_use=()):
        self.calls, self.in_use = [], set(in_use)
        super().__init__(self._answer)

    def _answer(self, argv, env, cwd, timeout):
        args = tuple(argv[1:])
        self.calls.append(args)
        out = ""
        if args[:2] == ("builder", "prune"):
            out = "ID\nTotal:\t6.01GB\n"
        elif args[:2] == ("image", "prune"):
            out = "Total reclaimed space: 1.5GB\n"
        elif args[0] == "ps":
            out = "abc\n" if args[-1].split("=", 1)[1] in self.in_use else ""
        elif args[:2] == ("image", "inspect"):
            out = "300000000\n"
        return subprocess.CompletedProcess(argv, 0, out, "")


def test_docker_cleanup_removes_only_what_mulebox_used_and_nothing_uses(paths):
    image_use.noted(paths, ["postgres:16", "redis:7"], NOW - 30 * DAY)
    image_use.noted(paths, ["mysql:8.4"], NOW)  # used today
    engine = FakeEngine(in_use={"redis:7"})
    freed = docker_prune.prune(engine, paths, 7, NOW)
    assert freed["build_cache"] == 6_010_000_000 and freed["removed"] == ["postgres:16"]
    assert freed["images"] == 1_500_000_000 + 300_000_000
    assert ("image", "rm", "postgres:16") in engine.calls
    assert not any(c[:2] == ("image", "rm") and c[2] != "postgres:16" for c in engine.calls)
    assert ("builder", "prune", "--force", "--filter", "until=168h") in engine.calls
    assert image_use.stale(paths, 7, NOW) == ["redis:7"]  # still noted, as a container uses it


def test_prune_is_refused_in_every_other_form():
    engine = FakeEngine()
    for args in (("image", "prune", "--all", "--force", "--filter", "until=1h"),
                 ("volume", "prune", "--force", "--filter", "until=1h"),
                 ("builder", "prune", "--force"), ("system", "prune", "--force"),
                 ("image", "prune", "--force", "--filter", "until=0h")):
        try:
            engine.run(*args)
        except DockerError:
            continue
        raise AssertionError(f"ran {args}")
    assert engine.calls == []


def test_the_images_a_compose_model_pulls():
    model = {"services": {"db": {"image": "postgres:16"}, "app": {"build": {}, "image": "mine"},
                          "cache": {"image": "redis:7"}}}
    assert image_use.images_of(model) == ["postgres:16", "redis:7"]
