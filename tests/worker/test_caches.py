"""Package caches: where they are, who may use them, and how they are given back."""

import json
from pathlib import Path

import pytest

from mulebox import cli
from mulebox.common import compose
from mulebox.common.compose import ComposeError
from mulebox.common.ids import new_id
from mulebox.common.safepath import RemovalDenied, UnsafePath
from mulebox.coordinator import needs
from mulebox.worker import caches, compose_policy, reclaim, runspec
from mulebox.worker.cleaner import Cleaner
from mulebox.worker.docker import Docker, DockerError
from mulebox.worker.ports import PortPool

from .fake_docker import FakeDocker, ok
from .fakes import claim_body

CHECKOUT = Path("/jobs/app/job/src")


def bind(source, **extra):
    return {"type": "bind", "source": str(source), "target": "/cache", **extra}


def model(*volumes):
    return {"name": "p", "services": {"api": {"image": "x", "volumes": list(volumes)}}}


def build(paths, tmp_path, wanted, env=None, project="example-app", docker=None):
    machine = runspec.Machine("build-1", paths, docker, PortPool())
    claim = {**claim_body(["true"], project=project), "needs": list(wanted), "env": env or {}}
    return runspec.build(machine, new_id("job"), claim, tmp_path, tmp_path / "out.log", [])


def test_every_worker_reports_the_caches_by_itself():
    assert "cache-pnpm" in compose.worker_capabilities(())
    assert "cache-composer" in compose.worker_capabilities(("docker",))


def test_a_machine_without_them_is_told_to_upgrade():
    workers = [{"worker": "build-1", "capabilities": ["docker", "compose-v1"], "last_seen": 0}]
    assert "upgrade" in needs.refusal(workers, ["cache-pnpm"])


def test_a_job_that_asks_gets_its_projects_folder_and_the_tools_setting(paths, tmp_path):
    spec, notes = build(paths, tmp_path, ["cache-pnpm"])
    folder = paths.cache / "packages" / "example-app" / "pnpm"
    assert folder.is_dir()
    assert spec.env["MULEBOX_CACHE_PNPM"] == str(folder)
    assert spec.env["pnpm_config_store_dir"] == str(folder)
    assert spec.env["npm_config_store_dir"] == str(folder)
    assert any("package cache pnpm" in note for note in notes)


def test_npm_uses_its_own_setting(paths, tmp_path):
    spec, _ = build(paths, tmp_path, ["cache-npm"])
    assert spec.env["npm_config_cache"] == str(paths.cache / "packages/example-app/npm")
    assert spec.env["MULEBOX_CACHE_NPM"] == spec.env["npm_config_cache"]


def test_composer_uses_its_own_setting(paths, tmp_path):
    spec, _ = build(paths, tmp_path, ["cache-composer"])
    assert spec.env["COMPOSER_CACHE_DIR"] == str(paths.cache / "packages/example-app/composer")


def test_nothing_changes_for_a_job_that_did_not_ask(paths, tmp_path):
    spec, notes = build(paths, tmp_path, [])
    assert not (paths.cache / "packages").exists()
    assert not [name for name in spec.env if "CACHE" in name or "store_dir" in name]
    assert notes == ()


def test_projects_do_not_share_a_folder(paths, tmp_path):
    one, _ = build(paths, tmp_path, ["cache-pnpm"], project="example-app")
    two, _ = build(paths, tmp_path, ["cache-pnpm"], project="other-app")
    assert one.env["MULEBOX_CACHE_PNPM"] != two.env["MULEBOX_CACHE_PNPM"]


def test_env_cannot_move_a_cache(paths, tmp_path):
    spec, _ = build(paths, tmp_path, ["cache-composer"], env={"COMPOSER_CACHE_DIR": "/elsewhere"})
    assert spec.env["COMPOSER_CACHE_DIR"] == str(paths.cache / "packages/example-app/composer")


def test_a_folder_a_job_turned_into_a_symlink_stops_the_next_job(paths, tmp_path):
    folder = paths.package_cache("example-app", "pnpm")
    folder.parent.mkdir(parents=True)
    other = paths.package_cache("other-app", "pnpm")
    other.mkdir(parents=True)
    folder.symlink_to(other)
    with pytest.raises(UnsafePath, match="symlink"):
        build(paths, tmp_path, ["cache-pnpm"])


def test_a_bad_project_name_gets_no_folder(paths):
    with pytest.raises(UnsafePath):
        caches.for_job(paths, "../other", ["cache-pnpm"])


# The compose policy


def test_a_services_own_cache_may_be_mounted_writable(paths):
    folder = caches.for_job(paths, "example-app", ["cache-pnpm"]).folders[0]
    compose_policy.check(model(bind(folder)), CHECKOUT, (folder,))


def test_without_asking_the_same_mount_stays_refused(paths):
    folder = caches.for_job(paths, "example-app", ["cache-pnpm"]).folders[0]
    with pytest.raises(ComposeError, match="writable"):
        compose_policy.check(model(bind(folder)), CHECKOUT)


def test_another_projects_cache_stays_refused(paths):
    mine = caches.for_job(paths, "example-app", ["cache-pnpm"]).folders[0]
    theirs = caches.for_job(paths, "other-app", ["cache-pnpm"]).folders[0]
    with pytest.raises(ComposeError, match="writable"):
        compose_policy.check(model(bind(theirs)), CHECKOUT, (mine,))
    with pytest.raises(ComposeError, match="writable"):
        compose_policy.check(model(bind(f"{mine}/../../other-app/pnpm")), CHECKOUT, (mine,))


def test_a_symlink_out_of_the_cache_stays_refused(paths, tmp_path):
    folder = caches.for_job(paths, "example-app", ["cache-pnpm"]).folders[0]
    (folder / "out").symlink_to(tmp_path)
    with pytest.raises(ComposeError, match="writable"):
        compose_policy.check(model(bind(folder / "out")), CHECKOUT, (folder,))


def test_an_external_volume_stays_refused_with_a_cache(paths):
    folder = caches.for_job(paths, "example-app", ["cache-composer"]).folders[0]
    data = {**model(), "volumes": {"composer_cache": {"external": True}}}
    with pytest.raises(ComposeError, match="external"):
        compose_policy.check(data, CHECKOUT, (folder,))


def test_a_compose_job_may_mount_what_it_asked_for(paths, tmp_path):
    daemon = FakeDocker()
    src = tmp_path / "job" / "src"
    src.mkdir(parents=True)
    folder = paths.package_cache("example-app", "pnpm")
    data = {**model(bind(folder)), "name": "x"}
    daemon.responses[("compose", "config")] = ok(json.dumps(data))
    env = {compose.COMPOSE_FILES_KEY: "docker-compose.yml"}
    spec, _ = build(paths, src, ["cache-pnpm"], env=env, docker=Docker(daemon))
    written = json.loads((tmp_path / "job" / "compose.mulebox.yml").read_text())
    assert written["services"]["api"]["volumes"][0]["bind"]["create_host_path"] is False
    assert spec.env["MULEBOX_CACHE_PNPM"] == str(folder)


# Giving caches back


def job_folder(paths):
    job_id = new_id("job")
    (paths.job_dir("example-app", job_id) / "src").mkdir(parents=True)
    return job_id


def helper_runs(daemon):
    return [call for call in daemon.calls if call[0] == "run"]


def test_a_compose_job_gives_the_projects_caches_back(paths):
    daemon = FakeDocker()
    folder = paths.packages_dir("example-app")
    (folder / "pnpm").mkdir(parents=True)
    Cleaner(paths, "build-1", Docker(daemon)).clean("example-app", job_folder(paths), True)
    runs = helper_runs(daemon)
    assert len(runs) == 1
    assert runs[0][runs[0].index("--mount") + 1] == f"type=bind,source={folder},target=/reclaim"


def test_no_helper_runs_for_a_project_without_caches_or_without_containers(paths):
    daemon = FakeDocker()
    Cleaner(paths, "build-1", Docker(daemon)).clean("example-app", job_folder(paths), True)
    paths.packages_dir("example-app").mkdir(parents=True)
    Cleaner(paths, "build-1", Docker(daemon)).clean("example-app", job_folder(paths), False)
    assert helper_runs(daemon) == []


def test_a_failed_give_back_does_not_hold_up_the_job(paths, monkeypatch):
    def fail(*args):
        raise DockerError("no daemon")

    monkeypatch.setattr(reclaim, "reclaim_cache", fail)
    paths.packages_dir("example-app").mkdir(parents=True)
    job_id = job_folder(paths)
    Cleaner(paths, "build-1", Docker(FakeDocker())).clean("example-app", job_id, True)
    assert not paths.job_dir("example-app", job_id).exists()


def test_the_helper_never_mounts_a_cache_that_is_a_symlink(paths, tmp_path):
    paths.packages_dir("example-app").parent.mkdir(parents=True)
    paths.packages_dir("example-app").symlink_to(tmp_path)
    with pytest.raises(UnsafePath, match="symlink"):
        reclaim.reclaim_cache(Docker(FakeDocker()), paths, "example-app", new_id("job"), "b")


# Listing and clearing


def fill(paths, project="example-app", tool="pnpm", size=2_000_000):
    folder = paths.package_cache(project, tool)
    folder.mkdir(parents=True)
    (folder / "blob").write_bytes(b"x" * size)
    return folder


def test_listing_shows_size_per_project_and_tool(paths):
    fill(paths)
    fill(paths, "other-app", "composer", 10)
    assert caches.listing(paths) == [("example-app", "pnpm", 2_000_000),
                                     ("other-app", "composer", 10)]


def test_clear_removes_one_project_only(paths):
    fill(paths)
    other = fill(paths, "other-app")
    caches.clear(paths, "example-app")
    assert not paths.packages_dir("example-app").exists()
    assert (other / "blob").exists()


def test_clear_stays_in_the_packages_folder(paths):
    with pytest.raises(UnsafePath):
        caches.clear(paths, "../../jobs")


def test_clear_uses_the_helper_for_files_it_cannot_delete(paths, monkeypatch):
    fill(paths)
    daemon = FakeDocker()
    real, seen = caches.remove_tree, []

    def denied_once(path, roots):
        seen.append(path)
        if len(seen) == 1:
            raise RemovalDenied("root owns it")
        real(path, roots)

    monkeypatch.setattr(caches, "remove_tree", denied_once)
    caches.clear(paths, "example-app", Docker(daemon))
    assert len(helper_runs(daemon)) == 1 and not paths.packages_dir("example-app").exists()


def _node_toml(tmp_path, roots_config):
    lines = ['name = "build-2"', 'roles = ["worker"]', 'coordinator = "build-1"', "[roots]"]
    lines += [f'{key} = "{value}"' for key, value in roots_config.items()]
    path = tmp_path / "node.toml"
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def test_cli_lists_and_clears(tmp_path, roots_config, paths, capsys):
    fill(paths)
    config = _node_toml(tmp_path, roots_config)
    assert cli.main(["cache", "list", "--config", config]) == 0
    assert capsys.readouterr().out == "example-app\tpnpm\t2.0 MB\n"
    assert cli.main(["cache", "clear", "example-app", "--config", config]) == 0
    assert not paths.packages_dir("example-app").exists()
    assert cli.main(["cache", "clear", "..", "--config", config]) == 2
