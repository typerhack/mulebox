"""`mulebox doctor` asks whether the machine can reach a project's registries."""

import socket

import pytest

from mulebox.coordinator import reach

from .test_api import call


def test_a_listening_port_is_reached_and_a_closed_one_is_not(store, staging):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        open_host = f"127.0.0.1:{server.getsockname()[1]}"
        with socket.socket() as spare:
            spare.bind(("127.0.0.1", 0))
            closed = f"127.0.0.1:{spare.getsockname()[1]}"
        reply = call(store, staging, "reach", hosts=[open_host, closed])
    assert reply.body["hosts"] == {open_host: True, closed: False}


def test_nothing_asked_is_nothing_answered(store, staging):
    assert call(store, staging, "reach", hosts=[]).body["hosts"] == {}


@pytest.mark.parametrize("hosts", ["ghcr.io", ["a b"], ["-x"], [1], ["h"] * (reach.MAX_HOSTS + 1)])
def test_only_a_short_list_of_host_names(store, staging, hosts):
    reply = call(store, staging, "reach", hosts=hosts)
    assert reply.body.get("code") == "bad_request" or reply.type == "error"
