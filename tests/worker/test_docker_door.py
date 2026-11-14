"""An isolated compose job's door to Docker (worker/door_rules.py, worker/docker_door.py)."""

import json
import shutil
import socket
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from mulebox.worker import docker_door, door_rules

LABEL = "mulebox.job=job-01ABC"


@pytest.mark.parametrize("method, path", [
    ("GET", "/_ping"), ("HEAD", "/v1.56/_ping"), ("GET", "/v1.56/version"), ("GET", "/info"),
])
def test_the_cli_may_ask_what_it_always_asks(method, path):
    assert door_rules.decide(method, path, LABEL, set()).allow


def test_the_container_list_shows_only_this_jobs_containers():
    query = 'filters={"label":["com.docker.compose.project=mulebox-x"]}&all=1'
    decision = door_rules.decide("GET", f"/v1.56/containers/json?{query}", LABEL, set())
    parts = urlsplit(decision.target)
    assert parts.path == "/v1.56/containers/json"
    sent = parse_qs(parts.query)
    assert sent["all"] == ["1"]
    assert json.loads(sent["filters"][0])["label"] == ["com.docker.compose.project=mulebox-x", LABEL]
    mapped = door_rules.decide("GET", '/containers/json?filters={"label":{"a=b":true}}', LABEL, set())
    assert json.loads(parse_qs(urlsplit(mapped.target).query)["filters"][0])["label"] == ["a=b", LABEL]


def test_a_container_call_waits_for_the_label_check():
    decision = door_rules.decide("POST", "/v1.56/containers/abc123/exec", LABEL, set())
    assert decision.allow and decision.container == "abc123" and decision.exec_create
    assert door_rules.decide("GET", "/containers/abc/logs?follow=1", LABEL, set()).container == "abc"


def test_an_exec_is_reached_only_once_the_door_made_it():
    assert not door_rules.decide("POST", "/v1.56/exec/e1/start", LABEL, set()).allow
    assert door_rules.decide("POST", "/v1.56/exec/e1/start", LABEL, {"e1"}).allow


@pytest.mark.parametrize("method, path", [
    ("POST", "/v1.56/containers/create"), ("POST", "/images/create?fromImage=alpine"),
    ("POST", "/build"), ("POST", "/volumes/create"), ("PUT", "/containers/abc/archive"),
    ("GET", "/containers/abc/archive"), ("DELETE", "/containers/abc"),
    ("POST", "/containers/abc/update"), ("GET", "/containers/abc/exec"), ("POST", "/networks/create"),
    ("GET", "/images/json"), ("POST", "/containers/abc/attach"), ("POST", "/session"),
])
def test_anything_that_reaches_past_the_job_is_refused(method, path):
    decision = door_rules.decide(method, path, LABEL, set())
    assert not decision.allow and "isolated job may not" in decision.why


def test_a_privileged_exec_is_refused():
    assert door_rules.exec_body_problem(b'{"Cmd":["sh"],"Privileged":true}')
    assert door_rules.exec_body_problem(b'{"Cmd":["sh"]}') is None
    assert door_rules.exec_body_problem(b"not json")


def test_the_label_is_read_from_inspect():
    assert door_rules.has_label(json.dumps({"Config": {"Labels": {"mulebox.job": "job-01ABC"}}})
                                .encode(), LABEL)
    assert not door_rules.has_label(b'{"Config": {"Labels": {"mulebox.job": "job-OTHER"}}}', LABEL)
    assert not door_rules.has_label(b"{}", LABEL)


class Engine:
    """A stand-in Docker engine on a Unix socket: records what reaches it."""

    def __init__(self, path: Path) -> None:
        self.seen: list[str] = []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(path))
        self.server.listen(8)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(conn,), daemon=True).start()

    def _one(self, conn):
        with conn:
            head, rest = docker_door.read_head(conn)
            words, _, headers = docker_door.parse_head(head)
            docker_door.read_body(conn, headers, rest)
            self.seen.append(f"{words[0]} {words[1]} close={headers.get('connection')}")
            path = words[1]
            if path.startswith("/containers/mine/json"):
                body = {"Config": {"Labels": {"mulebox.job": "job-01ABC"}}}
            elif path.startswith("/containers/theirs/json"):
                body = {"Config": {"Labels": {"mulebox.job": "job-OTHER"}}}
            elif path.endswith("/exec"):
                body = {"Id": "exec-1"}
            elif "/exec/exec-1/start" in path:
                conn.sendall(b"HTTP/1.1 101 UPGRADED\r\nContent-Type: application/vnd.docker.raw-stream"
                             b"\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n")
                conn.sendall(conn.recv(100).upper())  # echo what the exec's stdin got
                return
            else:
                body = []
            data = json.dumps(body).encode()
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         + f"Content-Length: {len(data)}\r\n\r\n".encode() + data)


@pytest.fixture
def door():
    folder = Path(tempfile.mkdtemp(prefix="mbd", dir="/tmp"))  # a socket path must be short
    engine = Engine(folder / "engine.sock")
    the_door = docker_door.Door("job-01ABC", str(folder / "engine.sock"))
    server = docker_door.listen(folder / "door.sock")

    def accept():
        while True:
            try:
                client, _ = server.accept()
            except OSError:
                return
            threading.Thread(target=the_door.serve, args=(client,), daemon=True).start()
    threading.Thread(target=accept, daemon=True).start()
    yield folder / "door.sock", engine
    server.close()
    engine.server.close()
    shutil.rmtree(folder)


def ask(path: Path, raw: bytes) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(5)
        conn.connect(str(path))
        conn.sendall(raw)
        out = b""
        while chunk := conn.recv(65536):
            out += chunk
        return out


def test_the_door_narrows_the_list_and_closes_every_connection(door):
    path, engine = door
    reply = ask(path, b"GET /v1.56/containers/json?all=1 HTTP/1.1\r\nHost: docker\r\n"
                      b"Connection: keep-alive\r\n\r\n")
    assert reply.startswith(b"HTTP/1.1 200")
    assert "mulebox.job%3Djob-01ABC" in engine.seen[0] and engine.seen[0].endswith("close=close")


def test_the_door_refuses_and_the_engine_never_hears_of_it(door):
    path, engine = door
    reply = ask(path, b"POST /v1.56/containers/create HTTP/1.1\r\nHost: docker\r\n"
                      b"Content-Length: 2\r\n\r\n{}")
    assert reply.startswith(b"HTTP/1.1 403") and b"may not" in reply
    assert engine.seen == []


def test_an_exec_in_the_jobs_own_container_works_end_to_end(door):
    path, engine = door
    body = b'{"Cmd":["sh"],"AttachStdin":true}'
    reply = ask(path, b"POST /v1.56/containers/mine/exec HTTP/1.1\r\nHost: docker\r\n"
                      + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    assert reply.startswith(b"HTTP/1.1 200") and b'"exec-1"' in reply
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(5)
        conn.connect(str(path))
        conn.sendall(b"POST /v1.56/exec/exec-1/start HTTP/1.1\r\nHost: docker\r\n"
                     b"Connection: Upgrade\r\nUpgrade: tcp\r\nContent-Length: 2\r\n\r\n{}")
        head = b""
        while b"\r\n\r\n" not in head:
            head += conn.recv(4096)
        conn.sendall(b"hello")
        assert conn.recv(100) == b"HELLO"


def test_another_jobs_container_and_a_foreign_exec_are_refused(door):
    path, engine = door
    reply = ask(path, b"POST /containers/theirs/exec HTTP/1.1\r\nHost: docker\r\n"
                      b"Content-Length: 2\r\n\r\n{}")
    assert reply.startswith(b"HTTP/1.1 403") and b"not this job's" in reply
    assert not any("/theirs/exec" in line for line in engine.seen)
    assert ask(path, b"POST /exec/exec-9/start HTTP/1.1\r\nHost: docker\r\n\r\n").startswith(
        b"HTTP/1.1 403")


def test_an_upgrade_is_not_passed_on_outside_an_execs_start(door):
    path, engine = door
    ask(path, b"GET /containers/json HTTP/1.1\r\nHost: docker\r\nConnection: Upgrade\r\n"
              b"Upgrade: tcp\r\n\r\n")
    assert engine.seen[-1].endswith("close=close")
