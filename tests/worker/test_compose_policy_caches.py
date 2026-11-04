"""Package caches in the compose policy, on the worker and in `mulebox doctor`."""

from pathlib import Path

import pytest

from mulebox.common.compose import ComposeError
from mulebox.worker import compose_policy

CACHE = Path("/srv/mulebox/cache/packages/example-app/pnpm")


def model(**service):
    return {"services": {"app": service}}


CACHE = Path("/srv/mulebox/cache/packages/example-app/pnpm")


def bind(source, read_only=False):
    return {"type": "bind", "source": source, "target": "/store", "read_only": read_only}


def test_doctor_lets_a_cache_folder_through_without_looking_anything_up(monkeypatch):
    def no_lookups(*_):
        raise AssertionError("no checkout means no filesystem lookups")

    monkeypatch.setattr(compose_policy.os, "stat", no_lookups)
    monkeypatch.setattr(compose_policy.os.path, "exists", no_lookups)
    monkeypatch.setattr(compose_policy.os.path, "realpath", no_lookups)
    compose_policy.check(model(volumes=[bind(str(CACHE))]), None, (CACHE,))
    compose_policy.check(model(volumes=[bind(f"{CACHE}/store/v10")]), None, (CACHE,))
    with pytest.raises(ComposeError):
        compose_policy.check(model(volumes=[bind("/srv/other")]), None, (CACHE,))


@pytest.mark.parametrize("source", [
    f"{CACHE}/../../other-app/pnpm", f"{CACHE}/../../../../../../etc", f"{CACHE}-other",
    "/srv/mulebox/cache/packages/example-app",
])
def test_no_spelling_of_a_path_gets_past_the_cache_as_written(source):
    with pytest.raises(ComposeError, match="writable"):
        compose_policy.check(model(volumes=[bind(source)]), None, (CACHE,))


def test_a_socket_as_written_is_refused_whichever_way_it_is_reached():
    for source in ("/var/run/docker.sock", f"{CACHE}/../../../../../../var/run/docker.sock"):
        with pytest.raises(ComposeError, match="socket"):
            compose_policy.check(model(volumes=[bind(source, True)]), None, (CACHE,))


def test_the_refusal_names_the_package_cache_with_and_without_a_checkout(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    for root in (checkout, None):
        with pytest.raises(ComposeError, match="a package cache"):
            compose_policy.check(model(volumes=[bind(str(outside))]), root)


@pytest.mark.parametrize("source", ["/srv/elsewhere", "/etc/hosts", "/var/run/docker.sock",
                                    "/srv/mulebox/cache/packages/example-app/pnpm/../composer"])
def test_doctor_refuses_all_that_the_worker_refuses(tmp_path, source):
    """What the text alone shows: the worker has a look as well, and may refuse more."""
    def verdict(root):
        try:
            compose_policy.check(model(volumes=[bind(source)]), root, (CACHE,))
        except ComposeError:
            return "refused"
        return "fine"

    assert verdict(tmp_path) == verdict(None) == "refused"
