"""The door an isolated compose job reaches Docker through (door_rules.py says what it lets by).

    python -m mulebox.worker.docker_door --listen <socket> --job <job id>

Run by the job's own unit (isolated.py) beside its container, so it lives and ends with the
job; the socket is mounted into the container as its `DOCKER_HOST`. One request per
connection: the door sets `Connection: close`, so a second request can never ride on one it
let by. An allowed request is passed to the node's engine and the two sides are joined as they
are, which also carries the raw stream of an exec. What it refuses is said on stderr, so it is in
the job's log.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
from pathlib import Path

from mulebox.common import compose, docker_socket
from mulebox.worker import door_rules

MAX_HEAD = 64 * 1024
MAX_BODY = 1024 * 1024
TIMEOUT_S = 30.0


class BadRequest(Exception):
    pass


def read_head(conn: socket.socket, buffered: bytes = b"") -> tuple[bytes, bytes]:
    """(the head up to its blank line, what came after it)."""
    data = buffered
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(65536)
        if not chunk:
            raise BadRequest("the connection closed before a whole request")
        data += chunk
        if len(data) > MAX_HEAD:
            raise BadRequest("the request head is too long")
    head, _, rest = data.partition(b"\r\n\r\n")
    return head, rest


def parse_head(head: bytes) -> tuple[str, list[str], dict[str, str]]:
    """(first line's words, header lines, headers by lowercase name)."""
    lines = head.decode("latin-1").split("\r\n")
    words = lines[0].split(" ")
    if len(words) != 3:
        raise BadRequest(f"not an HTTP request line: {lines[0][:80]!r}")
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if not sep:
            raise BadRequest("a header without a colon")
        headers[name.strip().lower()] = value.strip()
    return words, lines[1:], headers


def read_body(conn: socket.socket, headers: dict[str, str], rest: bytes) -> bytes:
    """A request's or reply's whole body, by Content-Length or chunks; for small ones only."""
    if "chunked" in headers.get("transfer-encoding", "").lower():
        return _chunks(conn, rest)
    size = int(headers.get("content-length") or 0)
    if size > MAX_BODY:
        raise BadRequest("the body is too large")
    while len(rest) < size:
        chunk = conn.recv(65536)
        if not chunk:
            break
        rest += chunk
    return rest[:size]


def _chunks(conn: socket.socket, data: bytes) -> bytes:
    out = b""
    while True:
        while b"\r\n" not in data:
            more = conn.recv(65536)
            if not more:
                return out
            data += more
        line, _, data = data.partition(b"\r\n")
        size = int(line.split(b";")[0] or b"0", 16)
        if size == 0:
            return out
        while len(data) < size + 2:
            more = conn.recv(65536)
            if not more:
                return out + data[:size]
            data += more
        out, data = out + data[:size], data[size + 2:]
        if len(out) > MAX_BODY:
            raise BadRequest("the body is too large")


def _answer(client: socket.socket, code: int, message: str) -> None:
    body = json.dumps({"message": message}).encode()
    client.sendall(f"HTTP/1.1 {code} Refused\r\nContent-Type: application/json\r\n"
                   f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)


def _request(method: str, target: str, header_lines: list[str], body: bytes,
             stream: bool = False) -> bytes:
    """The request as the engine gets it, with `Connection: close`. `stream`: an exec's start,
    which may ask to upgrade the connection to a raw stream; that is not HTTP any more, so no
    second request can follow there either. Anywhere else an upgrade is not passed on."""
    upgrade = stream and any(line.split(":", 1)[0].strip().lower() == "upgrade"
                             for line in header_lines)
    dropped = ("content-length", "transfer-encoding") + (() if upgrade else ("connection", "upgrade"))
    kept = [line for line in header_lines if line.split(":", 1)[0].strip().lower() not in dropped]
    lines = [f"{method} {target} HTTP/1.1", *kept, *(() if upgrade else ("Connection: close",))]
    if body or method in ("POST", "PUT"):
        lines.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body


class Door:
    def __init__(self, job_id: str, upstream: str) -> None:
        self.label = f"{compose.LABEL_JOB}={job_id}"
        self.upstream = upstream
        self.execs: set[str] = set()
        self.lock = threading.Lock()

    def _engine(self) -> socket.socket:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(TIMEOUT_S)
        conn.connect(self.upstream)
        return conn

    def _ask(self, method: str, target: str, body: bytes = b"") -> tuple[int, bytes]:
        """One whole request to the engine: (status, body)."""
        with self._engine() as conn:
            conn.sendall(_request(method, target, ["Host: docker"], body))
            head, rest = read_head(conn)
            words, _, headers = parse_head(head)
            return int(words[1]), read_body(conn, headers, rest)

    def _owned(self, container: str) -> bool:
        status, body = self._ask("GET", f"/containers/{container}/json")
        return status == 200 and door_rules.has_label(body, self.label)

    def serve(self, client: socket.socket) -> None:
        try:
            client.settimeout(TIMEOUT_S)
            head, rest = read_head(client)
            words, header_lines, headers = parse_head(head)
            method, path = words[0], words[1]
            with self.lock:
                execs = set(self.execs)
            decision = door_rules.decide(method, path, self.label, execs)
            if not decision.allow:
                print(decision.why, file=sys.stderr, flush=True)
                _answer(client, 403, decision.why)
                return
            if decision.container is not None and not self._owned(decision.container):
                why = f"mulebox: container {decision.container} is not this job's"
                print(why, file=sys.stderr, flush=True)
                _answer(client, 403, why)
                return
            body = read_body(client, headers, rest) if method in ("POST", "PUT") else b""
            if decision.exec_create:
                problem = door_rules.exec_body_problem(body)
                if problem:
                    print(problem, file=sys.stderr, flush=True)
                    _answer(client, 403, problem)
                    return
                self._exec_create(client, method, decision.target, header_lines, body)
                return
            stream = decision.exec_id is not None and decision.target.split("?")[0].endswith("/start")
            self._join(client, _request(method, decision.target, header_lines, body, stream))
        except (BadRequest, OSError, ValueError) as exc:
            try:
                _answer(client, 400, f"mulebox: {exc}")
            except OSError:
                pass
        finally:
            client.close()

    def _exec_create(self, client: socket.socket, method: str, target: str,
                     header_lines: list[str], body: bytes) -> None:
        with self._engine() as engine:
            engine.sendall(_request(method, target, header_lines, body))
            head, rest = read_head(engine)
            _, _, headers = parse_head(head)
            reply = read_body(engine, headers, rest)
        try:
            exec_id = json.loads(reply).get("Id")
        except (ValueError, AttributeError):
            exec_id = None
        if isinstance(exec_id, str):
            with self.lock:
                self.execs.add(exec_id)
        kept = [line for line in head.decode("latin-1").split("\r\n")
                if line.split(":", 1)[0].strip().lower()
                not in ("content-length", "transfer-encoding", "connection")]
        client.sendall(("\r\n".join([*kept, f"Content-Length: {len(reply)}",
                                     "Connection: close"]) + "\r\n\r\n").encode("latin-1") + reply)

    def _join(self, client: socket.socket, request: bytes) -> None:
        """Pass the request on, then copy both ways until the engine is done: an exec's
        stream stays open both ways, a plain reply ends when the engine closes."""
        engine = self._engine()
        engine.settimeout(None)
        client.settimeout(None)
        engine.sendall(request)
        up = threading.Thread(target=_copy, args=(client, engine), daemon=True)
        up.start()
        _copy(engine, client)
        engine.close()


def _copy(source: socket.socket, sink: socket.socket) -> None:
    try:
        while chunk := source.recv(65536):
            sink.sendall(chunk)
    except OSError:
        pass
    try:
        sink.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def listen(path: Path) -> socket.socket:
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)
    try:
        server.bind(str(path))
    finally:
        os.umask(old)
    server.listen(16)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docker_door")
    parser.add_argument("--listen", required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args(argv)
    upstream = docker_socket.socket_path()
    if upstream is None:
        print("mulebox: no Docker socket for the job's door", file=sys.stderr)
        return 1
    door = Door(args.job, upstream)
    server = listen(Path(args.listen))
    while True:
        client, _ = server.accept()
        threading.Thread(target=door.serve, args=(client,), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
