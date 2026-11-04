"""lan mode pieces without a server: password, sessions, limiter, firewall, setup checks."""

import ipaddress
import stat
import subprocess

import pytest

from mulebox.dashboard import cert, firewall, lan_commands, password
from mulebox.dashboard.lanfiles import LanNotReady, lan_dir
from mulebox.dashboard.session import (
    FIRST_WAIT_S, FREE_FAILURES, MAX_SESSIONS, MAX_WAIT_S, LanAccess, LoginLimiter, Sessions,
)

ADDRESS = "192.168.1.50"
DASH = {"lan_range": "192.168.1.0/24", "lan_address": ADDRESS, "lan_port": 8443}


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


def test_password_round_trip_and_never_stored_plain(tmp_path):
    path = password.save(tmp_path, "correct horse")
    stored = password.load(tmp_path)
    assert "correct horse" not in path.read_text()
    assert password.verify("correct horse", stored)
    assert not password.verify("wrong", stored)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700


@pytest.mark.parametrize("stored", ["", "plain", "scrypt$x$8$1$AA==$AA==", "md5$1$2$3$4$5"])
def test_verify_rejects_bad_files(stored):
    assert not password.verify("anything", stored)


def test_verify_refuses_huge_input_cheaply(tmp_path):
    password.save(tmp_path, "correct horse")
    assert not password.verify("x" * (password.MAX_LENGTH + 1), password.load(tmp_path))


def test_new_password_length():
    assert password.check_new("short")
    assert password.check_new("x" * (password.MAX_LENGTH + 1))
    assert password.check_new("long enough!") is None


def test_missing_password_names_the_command(tmp_path):
    with pytest.raises(LanNotReady, match="mulebox dashboard password"):
        password.load(tmp_path)


def test_sessions_expire_end_and_stay_bounded():
    clock = Clock()
    sessions = Sessions(clock, ttl=10)
    token = sessions.create()
    assert sessions.valid(token) and not sessions.valid("other") and not sessions.valid(None)
    clock.now += 11
    assert not sessions.valid(token)
    second = sessions.create()
    sessions.end(second)
    assert not sessions.valid(second)
    tokens = [sessions.create() for _ in range(MAX_SESSIONS + 1)]
    assert not sessions.valid(tokens[0]) and sessions.valid(tokens[-1])


def test_limiter_backs_off_per_address_and_resets():
    clock = Clock()
    limiter = LoginLimiter(clock)
    for _ in range(FREE_FAILURES):
        limiter.failed("a")
    assert limiter.retry_after("a") == 0
    limiter.failed("a")
    assert limiter.retry_after("a") == FIRST_WAIT_S
    limiter.failed("a")
    assert limiter.retry_after("a") == FIRST_WAIT_S * 2
    assert limiter.retry_after("b") == 0
    for _ in range(20):
        limiter.failed("a")
    assert limiter.retry_after("a") == MAX_WAIT_S
    limiter.succeeded("a")
    assert limiter.retry_after("a") == 0


@pytest.mark.parametrize("remote, ok", [("192.168.1.9", True), ("192.168.2.9", False),
                                        ("fd00::1", False), ("", False), (None, False),
                                        ("nonsense", False)])
def test_range_check(remote, ok):
    clock = Clock()
    access = LanAccess(ipaddress.ip_network("192.168.1.0/24"), frozenset({ADDRESS}),
                       (ADDRESS, 8443), "", Sessions(clock), LoginLimiter(clock))
    assert access.allows(remote) is ok


@pytest.mark.parametrize("sockname, lan", [((ADDRESS, 8443), True), (("127.0.0.1", 8090), False),
                                           (("127.0.0.1", 8443), False), ((ADDRESS, 1), False),
                                           ((ADDRESS, 8443, 0, 0), True), (None, True), ("x", True)])
def test_lan_socket_check_fails_closed(sockname, lan):
    clock = Clock()
    access = LanAccess(ipaddress.ip_network("192.168.1.0/24"), frozenset({ADDRESS}),
                       (ADDRESS, 8443), "", Sessions(clock), LoginLimiter(clock))
    assert access.is_lan_socket(sockname) is lan


def test_ruleset_only_touches_its_port_and_table():
    rules = firewall.ruleset("192.168.1.0/24", 8443)
    assert "tcp dport 8443 ip saddr != 192.168.1.0/24 drop" in rules
    assert "policy accept" in rules
    assert "flush" not in rules and "22" not in rules
    assert rules.count("table inet mulebox_dashboard") == 3


def test_script_validates_before_it_starts_anything():
    script = firewall.script("192.168.1.0/24", 8443)
    assert script.index("nft -c -f") < script.index("systemctl restart")
    assert "ufw" not in script and "rm " not in script


def _generate(tmp_path):
    return cert.generate(tmp_path, ADDRESS)


def test_certificate_fits_one_address_only(tmp_path):
    made = _generate(tmp_path)
    cert.check(tmp_path, ADDRESS)
    with pytest.raises(LanNotReady, match="--force"):
        cert.check(tmp_path, "192.168.1.51")
    assert stat.S_IMODE((tmp_path / cert.KEY_NAME).stat().st_mode) == 0o600
    text = subprocess.run(["openssl", "x509", "-in", str(made), "-noout", "-text"],
                          capture_output=True, text=True, check=True).stdout
    assert "Name Constraints: critical" in text and "pathlen:0" in text
    assert len(cert.fingerprint(made).split(":")) == 32
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


def test_missing_certificate_names_the_command(tmp_path):
    with pytest.raises(LanNotReady, match="mulebox dashboard cert"):
        cert.check(tmp_path, ADDRESS)


def test_prepare_says_which_step_is_missing(tmp_path):
    config = tmp_path / "node.toml"
    with pytest.raises(LanNotReady, match="password"):
        lan_commands.prepare(DASH, config)
    password.save(lan_dir(config), "correct horse")
    access, context = lan_commands.prepare(DASH, config)
    assert context is None and access.listen == (ADDRESS, 8443)


def test_prepare_with_tls_needs_the_certificate(tmp_path):
    config, dash = tmp_path / "node.toml", {**DASH, "lan_tls": True}
    password.save(lan_dir(config), "correct horse")
    with pytest.raises(LanNotReady, match="cert"):
        lan_commands.prepare(dash, config)
    cert.generate(lan_dir(config), ADDRESS)
    access, context = lan_commands.prepare(dash, config)
    assert access.hosts == {ADDRESS} and context is not None
