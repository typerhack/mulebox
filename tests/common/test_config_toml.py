"""Tests for the TOML configs: client.toml (laptop) and node.toml (build machine)."""

import pytest

from mulebox.common.config import (
    ClientConfig,
    ConfigError,
    NodeConfig,
    client_config_path,
    load_client_config,
    load_node_config,
    node_config_path,
)

ROOTS = """\
[roots]
jobs = "/home/alice/.mulebox/jobs"
cache = "/home/alice/.mulebox/cache"
staging = "/home/alice/.mulebox/staging"
runners = "/home/alice/.mulebox/runners"
"""

NODE = 'name = "build-1"\nroles = ["coordinator", "worker"]\n'


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("MULEBOX_CONFIG", raising=False)
    return home


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def client_error(tmp_path, text):
    path = write(tmp_path / "client.toml", text)
    with pytest.raises(ConfigError) as info:
        load_client_config(path)
    assert str(path) in str(info.value)
    return info.value


def node_error(tmp_path, top, tables=ROOTS):
    path = write(tmp_path / "node.toml", top + tables)
    with pytest.raises(ConfigError) as info:
        load_node_config(path)
    assert str(path) in str(info.value)
    return info.value


def load_node(tmp_path, text):
    return load_node_config(write(tmp_path / "node.toml", text))


# client.toml


def test_client_defaults(tmp_path):
    config = load_client_config(write(tmp_path / "c.toml", 'coordinator = "build-1"\n'))
    assert config == ClientConfig(coordinator="build-1")
    assert config.remote_bin == "~/.mulebox/bin/mulebox"
    assert config.connect_timeout_s == 10


def test_client_all_fields(tmp_path):
    text = 'coordinator = "alice@build-1"\nremote_bin = "/opt/mulebox/bin/mulebox"\n'
    config = load_client_config(write(tmp_path / "c.toml", text + "connect_timeout_s = 5\n"))
    assert config == ClientConfig("alice@build-1", "/opt/mulebox/bin/mulebox", 5)


def test_client_default_path_under_home(isolated_home):
    expected = isolated_home / ".config" / "mulebox" / "client.toml"
    assert client_config_path() == expected
    write(expected, 'coordinator = "build-1"\n')
    assert load_client_config().coordinator == "build-1"


def test_client_env_override(tmp_path, monkeypatch):
    path = write(tmp_path / "other.toml", 'coordinator = "build-2"\n')
    monkeypatch.setenv("MULEBOX_CONFIG", str(path))
    assert client_config_path() == path
    assert load_client_config().coordinator == "build-2"


def test_client_explicit_path_beats_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MULEBOX_CONFIG", str(tmp_path / "absent.toml"))
    path = write(tmp_path / "explicit.toml", 'coordinator = "build-3"\n')
    assert load_client_config(path).coordinator == "build-3"


def test_client_empty_env_is_ignored(isolated_home, monkeypatch):
    monkeypatch.setenv("MULEBOX_CONFIG", "")
    assert client_config_path() == isolated_home / ".config" / "mulebox" / "client.toml"


def test_client_missing_file_names_path(isolated_home):
    with pytest.raises(ConfigError) as info:
        load_client_config()
    assert "client.toml" in str(info.value) and "not found" in str(info.value)


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("", "coordinator"),
        ('coordinator = ""\n', "coordinator"),
        ("coordinator = 3\n", "coordinator"),
        ('coordinator = "-oProxyCommand=x"\n', "coordinator"),
        ('coordinator = "build 1"\n', "coordinator"),
        ('coordinator = "build-1"\nconnect_timeout_s = 0\n', "connect_timeout_s"),
        ('coordinator = "build-1"\nconnect_timeout_s = 301\n', "connect_timeout_s"),
        ('coordinator = "build-1"\nconnect_timeout_s = "5"\n', "connect_timeout_s"),
        ('coordinator = "build-1"\nremote_bin = ""\n', "remote_bin"),
        ('coordinator = "build-1"\nhost = "x"\n', "host"),
    ],
)
def test_client_invalid(tmp_path, text, field):
    assert client_error(tmp_path, text).field == field


def test_client_invalid_toml(tmp_path):
    assert "invalid TOML" in client_error(tmp_path, "coordinator = \n").problem


def test_client_not_utf8(tmp_path):
    path = tmp_path / "c.toml"
    path.write_bytes(b'coordinator = "\xff"\n')
    with pytest.raises(ConfigError, match="UTF-8"):
        load_client_config(path)


# node.toml


def test_node_minimal_defaults(tmp_path):
    config = load_node(tmp_path, NODE + ROOTS)
    assert config == NodeConfig(
        name="build-1",
        roles=("coordinator", "worker"),
        roots={k: f"/home/alice/.mulebox/{k}" for k in ("jobs", "cache", "staging", "runners")},
        dashboard={"mode": "local", "port": 8090, "lan_range": None, "lan_address": None,
                   "lan_port": 8443, "lan_tls": False},
    )
    assert config.slots == 1 and config.capabilities == () and config.coordinator is None


def test_node_full(tmp_path):
    top = (
        'name = "build-2"\nroles = ["worker"]\nslots = 4\n'
        'capabilities = ["docker", "arch:x86_64"]\ncoordinator = "build-1"\n'
    )
    dash = ('[dashboard]\nmode = "lan"\nport = 8091\nlan_range = "192.168.1.0/24"\n'
            'lan_address = "192.168.1.50"\nlan_port = 9443\nlan_tls = true\n')
    config = load_node(tmp_path, top + ROOTS + dash)
    assert config.roles == ("worker",) and config.slots == 4
    assert config.capabilities == ("docker", "arch:x86_64")
    assert config.coordinator == "build-1"
    assert config.dashboard == {"mode": "lan", "port": 8091, "lan_range": "192.168.1.0/24",
                                "lan_address": "192.168.1.50", "lan_port": 9443,
                                "lan_tls": True}


def test_node_default_path_under_home(isolated_home, monkeypatch, tmp_path):
    expected = isolated_home / ".config" / "mulebox" / "node.toml"
    assert node_config_path() == expected
    monkeypatch.setenv("MULEBOX_CONFIG", str(tmp_path / "client.toml"))
    write(expected, NODE + ROOTS)
    assert load_node_config().name == "build-1"


def test_node_ipv6_lan_range_normalised(tmp_path):
    dash = '[dashboard]\nlan_range = "FD00:0:0:0::/64"\n'
    assert load_node(tmp_path, NODE + ROOTS + dash).dashboard["lan_range"] == "fd00::/64"


@pytest.mark.parametrize("mode", ["off", "local"])
def test_node_dashboard_modes(tmp_path, mode):
    config = load_node(tmp_path, NODE + ROOTS + f'[dashboard]\nmode = "{mode}"\n')
    assert config.dashboard["mode"] == mode


@pytest.mark.parametrize(
    ("top", "field"),
    [
        ('roles = ["worker"]\ncoordinator = "build-1"\n', "name"),
        ('name = "build 1"\nroles = ["worker"]\n', "name"),
        ('name = "build-1"\n', "roles"),
        ('name = "build-1"\nroles = []\n', "roles"),
        ('name = "build-1"\nroles = ["boss"]\n', "roles"),
        ('name = "build-1"\nroles = ["worker", "worker"]\ncoordinator = "b"\n', "roles"),
        ('name = "build-1"\nroles = "worker"\n', "roles"),
        (NODE + "slots = 0\n", "slots"),
        (NODE + "slots = 1.5\n", "slots"),
        (NODE + "slots = true\n", "slots"),
        (NODE + "capabilities = [1]\n", "capabilities[0]"),
        (NODE + 'coordinator = "-x"\n', "coordinator"),
        ('name = "build-2"\nroles = ["worker"]\n', "coordinator"),
        (NODE + 'colour = "blue"\n', "colour"),
    ],
)
def test_node_invalid_top_level(tmp_path, top, field):
    assert node_error(tmp_path, top).field == field


def test_node_roots_required(tmp_path):
    assert node_error(tmp_path, NODE, tables="").field == "roots"


@pytest.mark.parametrize(
    ("line", "field"),
    [
        ('jobs = "relative/jobs"', "roots.jobs"),
        ('jobs = "~/jobs"', "roots.jobs"),
        ('jobs = "/"', "roots.jobs"),
        ('jobs = "/home/alice/../etc"', "roots.jobs"),
        ("jobs = 5", "roots.jobs"),
    ],
)
def test_node_invalid_roots(tmp_path, line, field):
    roots = ROOTS.replace('jobs = "/home/alice/.mulebox/jobs"', line)
    assert node_error(tmp_path, NODE, roots).field == field


def test_node_missing_root_key(tmp_path):
    roots = ROOTS.replace('runners = "/home/alice/.mulebox/runners"\n', "")
    assert node_error(tmp_path, NODE, roots).field == "roots.runners"


def test_node_unknown_root_key(tmp_path):
    err = node_error(tmp_path, NODE, ROOTS + 'logs = "/home/alice/logs"\n')
    assert err.field == "roots.logs" and "unknown key" in err.problem


@pytest.mark.parametrize(
    ("dash", "field"),
    [
        ('mode = "public"', "dashboard.mode"),
        ("mode = 1", "dashboard.mode"),
        ('mode = "lan"', "dashboard.lan_range"),
        ('mode = "lan"\nlan_range = "192.168.1.0"', "dashboard.lan_range"),
        ('mode = "lan"\nlan_range = "192.168.1.5/24"', "dashboard.lan_range"),
        ('mode = "lan"\nlan_range = "not-a-network"', "dashboard.lan_range"),
        ('mode = "lan"\nlan_range = "192.168.1.0/33"', "dashboard.lan_range"),
        ('lan_range = "0.0.0.0/0"', "dashboard.lan_range"),
        ('lan_range = "8.8.8.0/24"', "dashboard.lan_range"),
        ('mode = "lan"\nlan_range = "192.168.1.0/24"', "dashboard.lan_address"),
        ('lan_range = "192.168.1.0/24"\nlan_address = "192.168.2.5"', "dashboard.lan_address"),
        ('lan_range = "192.168.1.0/24"\nlan_address = "nope"', "dashboard.lan_address"),
        ('lan_range = "fd00::/64"\nlan_address = "fd00::1"', "dashboard.lan_address"),
        ('lan_address = "192.168.1.5"', "dashboard.lan_range"),
        ("port = 8443", "dashboard.lan_port"),
        ('lan_tls = "yes"', "dashboard.lan_tls"),
        ("port = 0", "dashboard.port"),
        ("port = 65536", "dashboard.port"),
        ('port = "8090"', "dashboard.port"),
        ('password = "x"', "dashboard.password"),
    ],
)
def test_node_invalid_dashboard(tmp_path, dash, field):
    assert node_error(tmp_path, NODE, ROOTS + f"[dashboard]\n{dash}\n").field == field


def test_node_dashboard_must_be_table(tmp_path):
    assert node_error(tmp_path, NODE + 'dashboard = "lan"\n').field == "dashboard"
