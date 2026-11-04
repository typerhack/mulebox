"""What a compose model may not do. Models are shaped as `docker compose config` prints them."""

import os
import socket
import tempfile
from pathlib import Path

import pytest

from mulebox.common.compose import ComposeError
from mulebox.worker import compose_policy

CHECKOUT = Path("/jobs/app/job/src")


def model(**service):
    return {"name": "p", "services": {"api": {"image": "x", **service}, "db": {"image": "y"}}}


def refused(data):
    with pytest.raises(ComposeError) as caught:
        compose_policy.check(data, CHECKOUT)
    return str(caught.value)


@pytest.mark.parametrize("field,value", [
    ("network_mode", "host"), ("pid", "host"), ("ipc", "host"), ("uts", "host"),
    ("userns_mode", "host"), ("cgroup", "host"),
    ("network_mode", "container:personal-db"), ("pid", "container:personal-db"),
    ("ipc", "container:personal-db"), ("network_mode", "ns:/proc/1/ns/net"),
])
def test_foreign_namespaces_are_refused(field, value):
    assert value in refused(model(**{field: value}))


@pytest.mark.parametrize("field", ["network_mode", "pid", "ipc"])
def test_a_namespace_of_another_service_is_fine_if_it_exists(field):
    compose_policy.check(model(**{field: "service:db"}), CHECKOUT)
    assert "no service" in refused(model(**{field: "service:ghost"}))


@pytest.mark.parametrize("field,value", [
    ("network_mode", "bridge"), ("network_mode", "none"), ("ipc", "shareable"),
    ("cgroup", "private"), ("network_mode", None),
])
def test_ordinary_namespace_values_are_fine(field, value):
    compose_policy.check(model(**{field: value}), CHECKOUT)


@pytest.mark.parametrize("field,value,word", [
    ("privileged", True, "privileged"),
    ("devices", [{"source": "/dev/sda", "target": "/dev/sda"}], "devices"),
    ("device_cgroup_rules", ["b 8:* rmw"], "devices"),
    ("gpus", [{"driver": "nvidia"}], "GPU"),
    ("cgroup_parent", "/system.slice", "control group"),
    ("external_links", ["personal-db:db"], "outside the project"),
    ("use_api_socket", True, "Docker API"),
    ("provider", {"type": "model"}, "provider"),
    ("runtime", "custom", "runtime"),
])
def test_doors_out_of_the_container_are_refused(field, value, word):
    assert word in refused(model(**{field: value}))


def test_keys_set_to_nothing_are_fine():
    compose_policy.check(model(privileged=False, devices=[], cap_add=[]), CHECKOUT)


@pytest.mark.parametrize("entry", ["container:personal-db", "container:personal-db:ro"])
def test_volumes_from_outside_the_project_is_refused(entry):
    assert "outside the project" in refused(model(volumes_from=[entry]))


@pytest.mark.parametrize("entry", ["db", "db:ro", "db:rw"])
def test_volumes_from_a_service_is_fine(entry):
    compose_policy.check(model(volumes_from=[entry]), CHECKOUT)


def test_volumes_from_an_unknown_service_is_refused():
    assert "ghost" in refused(model(volumes_from=["ghost"]))


@pytest.mark.parametrize("name", ["SYS_ADMIN", "ALL", "NET_ADMIN", "SYS_MODULE", "SYS_RAWIO",
                                  "cap_sys_admin", "DAC_READ_SEARCH", "BPF"])
def test_strong_capabilities_are_refused(name):
    assert name in refused(model(cap_add=[name]))


@pytest.mark.parametrize("name", ["SYS_NICE", "CAP_SYS_NICE", "sys_ptrace", "IPC_LOCK", "CHOWN"])
def test_harmless_capabilities_are_fine(name):
    compose_policy.check(model(cap_add=[name]), CHECKOUT)


@pytest.mark.parametrize("option", ["seccomp=unconfined", "seccomp:unconfined",
                                    "apparmor=unconfined", "label=disable",
                                    "systempaths=unconfined"])
def test_turning_off_container_security_is_refused(option):
    assert option in refused(model(security_opt=[option]))


@pytest.mark.parametrize("option", ["no-new-privileges", "no-new-privileges:true"])
def test_tightening_container_security_is_fine(option):
    compose_policy.check(model(security_opt=[option]), CHECKOUT)


@pytest.mark.parametrize("build,word", [
    ({"context": ".", "network": "host"}, "network: host"),
    ({"context": ".", "privileged": True}, "privileged"),
    ({"context": ".", "entitlements": ["network.host"]}, "entitlements"),
    ({"context": ".", "ssh": ["default"]}, "SSH"),
    ({"context": ".", "cache_to": ["type=local,dest=/srv/cache"]}, "cache_to"),
])
def test_a_build_cannot_reach_out_either(build, word):
    assert word in refused(model(build=build))


def test_an_ordinary_build_is_fine():
    compose_policy.check(model(build={"context": ".", "args": {"A": "1"}}), CHECKOUT)


@pytest.mark.parametrize("hook", ["pre_start", "post_start", "pre_stop"])
def test_privileged_hooks_are_refused(hook):
    assert hook in refused(model(**{hook: [{"command": ["id"], "privileged": True}]}))
    compose_policy.check(model(**{hook: [{"command": ["id"]}]}), CHECKOUT)


@pytest.mark.parametrize("kind", ["npipe", "cluster"])
def test_unknown_volume_types_are_refused(kind):
    assert kind in refused(model(volumes=[{"type": kind, "source": "x", "target": "/x"}]))


@pytest.mark.parametrize("source", ["/run/docker.sock", "/var/run/docker.sock", "/run", "/var/run",
                                    "/"])
def test_a_folder_holding_the_socket_is_refused_even_read_only(source):
    volume = {"type": "bind", "source": source, "target": "/s", "read_only": True}
    assert "socket" in refused(model(volumes=[volume]))


def test_relabelling_an_outside_folder_is_refused():
    volume = {"type": "bind", "source": "/etc", "target": "/e", "read_only": True,
              "bind": {"selinux": "z"}}
    assert "relabels" in refused(model(volumes=[volume]))


@pytest.mark.parametrize("driver", ["macvlan", "ipvlan", "overlay", "host"])
def test_networks_stay_on_the_bridge_driver(driver):
    data = {**model(), "networks": {"lan": {"driver": driver}}}
    assert driver in refused(data)


def test_a_bridge_network_is_fine():
    data = {**model(), "networks": {"a": {"driver": "bridge"}, "b": {}, "default": None}}
    compose_policy.check(data, CHECKOUT)


def test_volumes_stay_on_the_local_driver():
    assert "nfs-plugin" in refused({**model(), "volumes": {"v": {"driver": "nfs-plugin"}}})
    compose_policy.check({**model(), "volumes": {"v": {"driver": "local"}, "w": None}}, CHECKOUT)


@pytest.mark.parametrize("section", ["secrets", "configs"])
def test_external_secrets_and_configs_are_refused(section):
    assert "external" in refused({**model(), section: {"s": {"external": True}}})


@pytest.mark.parametrize("section", ["secrets", "configs"])
def test_a_secret_cannot_be_the_docker_socket(section):
    data = {**model(), section: {"s": {"file": "/var/run/docker.sock"}}}
    assert "socket" in refused(data)


def test_a_refusal_names_the_service():
    assert refused(model(privileged=True)).startswith("service api ")


GPU = [{"driver": "nvidia", "count": "all", "capabilities": ["gpu"]}]


@pytest.mark.parametrize("kind", ["limits", "reservations"])
@pytest.mark.parametrize("key,value", [("devices", GPU),
                                       ("generic_resources", [{"discrete_resource_spec": {}}])])
def test_host_hardware_through_deploy_is_refused(kind, key, value):
    data = model(deploy={"resources": {kind: {key: value}}})
    assert f"{kind}.{key}" in refused(data)


def test_ordinary_deploy_limits_are_fine():
    compose_policy.check(model(deploy={"replicas": 1, "resources": {
        "limits": {"cpus": "1", "memory": "512M"}, "reservations": {"memory": "128M"}}}), CHECKOUT)


@pytest.mark.parametrize("source", [
    "/run/containerd/containerd.sock", "/run/containerd", "/run/crio/crio.sock", "/run/crio",
    "/var/run/crio/crio.sock", "/run/podman/podman.sock", "/run/podman",
    "/run/k3s/containerd", "/run/buildkit", f"/run/user/{os.getuid()}/podman",
    f"/run/user/{os.getuid()}", "/run/user", f"/run/user/{os.getuid()}/buildkit",
    "/var/run/anything-else",
])
def test_other_runtimes_are_refused_whether_or_not_they_exist_here(source):
    volume = {"type": "bind", "source": source, "target": "/s", "read_only": True}
    assert "socket" in refused(model(volumes=[volume]))


@pytest.fixture
def unix_socket():
    """A short path: Unix socket paths are limited, and pytest's are long."""
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="mb") as folder:
        path = Path(folder) / "any.sock"
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(path))
            yield path


@pytest.mark.parametrize("read_only", [True, False])
def test_any_unix_socket_is_refused_by_its_type(unix_socket, read_only):
    volume = {"type": "bind", "source": str(unix_socket), "target": "/s", "read_only": read_only}
    assert "socket" in refused(model(volumes=[volume]))


def test_a_socket_inside_the_checkout_is_refused_too(unix_socket):
    volume = {"type": "bind", "source": str(unix_socket), "target": "/s"}
    with pytest.raises(ComposeError, match="socket"):
        compose_policy.check(model(volumes=[volume]), unix_socket.parent)


def test_a_symlink_to_a_socket_is_refused(unix_socket, tmp_path):
    link = tmp_path / "innocent"
    link.symlink_to(unix_socket)
    volume = {"type": "bind", "source": str(link), "target": "/s", "read_only": True}
    assert "socket" in refused(model(volumes=[volume]))


def test_a_secret_cannot_be_a_socket(unix_socket):
    assert "socket" in refused({**model(), "secrets": {"s": {"file": str(unix_socket)}}})


def test_an_ordinary_read_only_folder_is_fine(tmp_path):
    volume = {"type": "bind", "source": str(tmp_path), "target": "/s", "read_only": True}
    compose_policy.check(model(volumes=[volume]), CHECKOUT)


@pytest.mark.parametrize("volume", [
    {"type": "bind", "source": "/etc/data", "target": "/d"},
    {"type": "bind", "source": "../sibling", "target": "/d"},
    {"type": "bind", "source": "~/data", "target": "/d"},
    {"type": "bind", "source": "/var/run/docker.sock", "target": "/s", "read_only": True},
    {"type": "bind", "source": "/run/x", "target": "/s", "read_only": True},
    {"type": "bind", "source": "/opt", "target": "/o", "read_only": True,
     "bind": {"selinux": "z"}},
])
def test_without_a_checkout_what_a_bind_shows_is_refused(volume):
    with pytest.raises(ComposeError):
        compose_policy.check(model(volumes=[volume]), None)


@pytest.mark.parametrize("volume", [
    {"type": "bind", "source": "src", "target": "/d"},
    {"type": "bind", "source": "/opt/data", "target": "/d", "read_only": True},
    {"type": "volume", "source": "data", "target": "/d"},
])
def test_without_a_checkout_nothing_on_this_machine_is_asked(volume, monkeypatch):
    def no_lookups(*_args):
        raise AssertionError("looked at this machine")

    monkeypatch.setattr(compose_policy.os, "stat", no_lookups)
    monkeypatch.setattr(compose_policy.os.path, "exists", no_lookups)
    monkeypatch.setattr(compose_policy.os.path, "realpath", no_lookups)
    compose_policy.check(model(volumes=[volume]), None)


def test_without_a_checkout_a_secret_file_is_for_the_worker_to_judge():
    data = {"services": {}, "secrets": {"key": {"file": "/nowhere/key"}}}
    compose_policy.check(data, None)
    with pytest.raises(ComposeError):
        compose_policy.check({"services": {}, "secrets": {"key": {"external": True}}}, None)
