"""Where the dashboard is, as the build machine says it and the client prints it."""

from mulebox.common.dashboard_address import hint, place, where

LAN = {"mode": "lan", "lan_address": "192.168.1.50", "lan_port": 8090, "lan_tls": False}
JOB = "job-01EXAMPLE"


def test_lan_gives_its_address_and_a_job_page():
    info = where(LAN)
    assert place(info) == "http://192.168.1.50:8090"
    assert place(info, JOB) == f"http://192.168.1.50:8090/#/job/{JOB}"


def test_tls_changes_the_scheme():
    assert place(where({**LAN, "lan_tls": True})).startswith("https://")


def test_local_points_at_the_tunnel_command():
    assert hint(where({"mode": "local", "port": 8090})) == (
        "see it on the dashboard: mulebox dashboard open")


def test_off_and_an_older_coordinator_say_nothing():
    assert where({"mode": "off"}) is None
    assert hint(None) is None and hint("junk") is None
