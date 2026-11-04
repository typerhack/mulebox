"""The rewritten compose model: nothing a job does can collide with the machine."""

import copy

import pytest

from mulebox.common.compose import ComposeError
from mulebox.worker import compose_file
from mulebox.worker.compose_file import Port, published_ports, rewrite

JOB_ID = "job-01M6JW0YXQ5TASH2X7D95J4H8Z"
PROJECT = "mulebox-job-01m6jw0yxq5tash2x7d95j4h8z"
LABELS = {"mulebox.job": JOB_ID, "mulebox.worker": "build-1"}


def model(**service):
    base = {"image": "redis:7-alpine"}
    return {"name": PROJECT, "services": {"api": {**base, **service}},
            "networks": {"default": {"name": f"{PROJECT}_default", "ipam": {}}}}


def tcp(target, published="8000", **extra):
    return {"mode": "ingress", "target": target, "published": published, "protocol": "tcp", **extra}


def run(data, assigned=None, checkout="/jobs/app/job/src"):
    from pathlib import Path

    return rewrite(data, JOB_ID, LABELS, assigned or {}, Path(checkout))


def test_port_variables():
    assert Port("api", 8000, "tcp").variable == "MULEBOX_PORT_API_8000"
    assert Port("my-web.app", 80, "tcp").variable == "MULEBOX_PORT_MY_WEB_APP_80"
    assert Port("dns", 53, "udp").variable == "MULEBOX_PORT_DNS_53_UDP"


def test_published_ports_are_listed_once():
    data = model(ports=[tcp(80, "8000"), tcp(80, "8001"), tcp(443, "8443")])
    assert [p.target for p in published_ports(data)] == [80, 443]


def test_two_services_may_not_share_a_variable():
    data = model(ports=[tcp(80)])
    data["services"]["API"] = {"image": "x", "ports": [tcp(80)]}
    with pytest.raises(ComposeError, match="rename"):
        published_ports(data)


def test_no_services_is_an_error():
    with pytest.raises(ComposeError, match="no services"):
        published_ports({"name": PROJECT})


@pytest.mark.parametrize("given", [
    tcp(80, "8000"),
    tcp(80, "8000", host_ip="0.0.0.0"),
    tcp(80, "8000", host_ip="192.168.1.50"),
    tcp(80, "27017", host_ip="127.0.0.1"),
    {"mode": "ingress", "target": 80, "protocol": "tcp"},
])
def test_every_port_ends_up_on_loopback_on_the_chosen_port(given):
    result, _ = run(model(ports=[given]), {"MULEBOX_PORT_API_80": 24680})
    entry = result["services"]["api"]["ports"][0]
    assert entry["host_ip"] == "127.0.0.1" and entry["published"] == "24680"
    assert entry["target"] == 80


def test_two_host_ports_for_one_target_become_one():
    result, _ = run(model(ports=[tcp(80, "8000"), tcp(80, "8001")]),
                    {"MULEBOX_PORT_API_80": 24680})
    assert len(result["services"]["api"]["ports"]) == 1


def test_a_service_without_ports_stays_without():
    result, _ = run(model())
    assert "ports" not in result["services"]["api"]


def test_labels_reach_services_builds_networks_and_volumes():
    data = model(labels={"mine": "1"}, build={"context": "/jobs/app/job/src"})
    data["volumes"] = {"db": {"name": f"{PROJECT}_db"}}
    result, _ = run(data)
    api = result["services"]["api"]
    assert api["labels"] == {"mine": "1", **LABELS}
    assert api["build"]["labels"] == LABELS
    assert result["networks"]["default"]["labels"] == LABELS
    assert result["volumes"]["db"]["labels"] == LABELS


@pytest.mark.parametrize("section", ["networks", "volumes"])
def test_a_fixed_name_cannot_be_shared_between_jobs(section):
    data = model()
    data[section] = {"thing": {"name": "shared_for_everyone"}}
    result, _ = run(data)
    assert result[section]["thing"]["name"] == f"{PROJECT}_thing"


@pytest.mark.parametrize("section", ["networks", "volumes"])
def test_external_resources_are_refused(section):
    data = model()
    data[section] = {"thing": {"name": "x", "external": True}}
    with pytest.raises(ComposeError, match="external"):
        run(data)


def test_a_volume_backed_by_a_host_folder_is_refused():
    data = model()
    data["volumes"] = {"db": {"driver_opts": {"type": "none", "o": "bind", "device": "/srv/db"}}}
    with pytest.raises(ComposeError, match="host device"):
        run(data)


def test_container_name_is_dropped_and_the_job_is_told():
    result, notes = run(model(container_name="mysql"))
    assert "container_name" not in result["services"]["api"]
    assert "mysql" in notes[0] and "docker compose exec -T api" in notes[0]


def test_the_project_name_is_forced():
    data = model()
    data["name"] = "something-else"
    assert run(data)[0]["name"] == PROJECT


def test_the_input_is_not_changed():
    data = model(ports=[tcp(80)], container_name="x")
    before = copy.deepcopy(data)
    run(data, {"MULEBOX_PORT_API_80": 24680})
    assert data == before


@pytest.mark.parametrize("field,value,word", [
    ("network_mode", "host", "network_mode"), ("pid", "host", "pid"), ("ipc", "host", "ipc"),
    ("privileged", True, "privileged"),
])
def test_what_reaches_past_the_job_is_refused(field, value, word):
    with pytest.raises(ComposeError, match=word) as info:
        run(model(**{field: value}))
    assert "service api" in str(info.value)


def test_a_normal_network_mode_is_fine():
    assert run(model(network_mode="bridge"))[0]["services"]["api"]["network_mode"] == "bridge"


def bind(source, **extra):
    return {"type": "bind", "source": source, "target": "/app", "bind": {}, **extra}


def test_binds_inside_the_checkout_are_fine(tmp_path):
    checkout = tmp_path / "src"
    (checkout / "storage").mkdir(parents=True)
    run(model(volumes=[bind(str(checkout)), bind(str(checkout / "storage"))]),
        checkout=str(checkout))


@pytest.mark.parametrize("source", ["/home/alice", "/var/lib/mysql", "/etc"])
def test_a_writable_bind_outside_the_checkout_is_refused(source):
    with pytest.raises(ComposeError, match="outside the checkout"):
        run(model(volumes=[bind(source)]))


def test_a_bind_that_escapes_by_dotdot_or_symlink_is_refused(tmp_path):
    checkout = tmp_path / "src"
    checkout.mkdir()
    (checkout / "out").symlink_to(tmp_path)
    for source in (str(checkout / ".." / "other"), str(checkout / "out" / "x")):
        with pytest.raises(ComposeError, match="outside the checkout"):
            run(model(volumes=[bind(source)]), checkout=str(checkout))


def test_a_read_only_bind_outside_never_creates_its_source(tmp_path):
    volume = {"type": "bind", "source": str(tmp_path), "target": "/seed", "read_only": True,
              "bind": {"create_host_path": True, "propagation": "rprivate"}}
    result, _ = run(model(volumes=[volume]))
    assert result["services"]["api"]["volumes"][0]["bind"] == {
        "create_host_path": False, "propagation": "rprivate"}
    assert result["services"]["api"]["volumes"][0]["read_only"] is True
    assert volume["bind"]["create_host_path"] is True  # the input stays as it was


def test_a_read_only_bind_without_a_bind_section_is_sealed_too(tmp_path):
    volume = {"type": "bind", "source": str(tmp_path), "target": "/seed", "read_only": True}
    result, _ = run(model(volumes=[volume]))
    assert result["services"]["api"]["volumes"][0]["bind"] == {"create_host_path": False}


def test_a_missing_outside_source_is_refused(tmp_path):
    gone = tmp_path / "missing-cache"
    volume = {"type": "bind", "source": str(gone), "target": "/c", "read_only": True,
              "bind": {"create_host_path": True}}
    with pytest.raises(ComposeError, match="does not exist"):
        run(model(volumes=[volume]))
    assert not gone.exists()


def test_a_missing_source_inside_the_checkout_may_be_created(tmp_path):
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "storage"
    volume = {"type": "bind", "source": str(source), "target": "/s",
              "bind": {"create_host_path": True}}
    result, _ = run(model(volumes=[volume]), checkout=tmp_path / "src")
    assert result["services"]["api"]["volumes"][0]["bind"]["create_host_path"] is True


@pytest.mark.parametrize("section", ["secrets", "configs"])
def test_a_missing_outside_file_is_refused(tmp_path, section):
    data = {**model(), section: {"s": {"file": str(tmp_path / "gone")}}}
    with pytest.raises(ComposeError, match="does not exist"):
        run(data)


def test_a_read_only_bind_outside_is_allowed():
    run(model(volumes=[bind("/etc/localtime", read_only=True)]))


@pytest.mark.parametrize("read_only", [False, True])
def test_the_docker_socket_is_refused_even_read_only(read_only):
    with pytest.raises(ComposeError, match="Docker socket"):
        run(model(volumes=[bind("/var/run/docker.sock", read_only=read_only)]))


def test_named_volumes_and_tmpfs_are_no_binds():
    run(model(volumes=[{"type": "volume", "source": "db", "target": "/d"},
                       {"type": "tmpfs", "target": "/t"}]))


def test_the_prefix_matches_jobspec():
    from mulebox.worker import jobspec

    assert compose_file.PORT_PREFIX == jobspec._PORT_PREFIX
