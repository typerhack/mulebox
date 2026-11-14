"""localhost ports forwarded to services inside an isolated compose job (port_forward.py)."""

import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from mulebox.worker import port_forward

SCRIPT = Path(port_forward.__file__)


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_a_spec_names_both_ends():
    assert port_forward.parse("127.0.0.1:41000=db:5432") == ("127.0.0.1", 41000, "db", 5432)
    with pytest.raises(ValueError):
        port_forward.parse("db:5432")


def test_a_connection_to_the_local_port_reaches_the_service():
    service = socket.socket()
    service.bind(("127.0.0.1", 0))
    service.listen(1)
    target = service.getsockname()[1]

    def echo():
        conn, _ = service.accept()
        with conn:
            conn.sendall(conn.recv(100)[::-1])
    threading.Thread(target=echo, daemon=True).start()
    local = free_port()
    # run as the container runs it: a file of its own, with nothing of mulebox importable
    proc = subprocess.Popen([sys.executable, "-I", str(SCRIPT), f"127.0.0.1:{local}=127.0.0.1:{target}"],
                            stdout=subprocess.PIPE, text=True)
    try:
        assert "forwarded" in proc.stdout.readline()
        with socket.create_connection(("127.0.0.1", local), timeout=5) as conn:
            conn.sendall(b"abc")
            assert conn.recv(100) == b"cba"
    finally:
        proc.terminate()
        proc.wait(5)
        service.close()
