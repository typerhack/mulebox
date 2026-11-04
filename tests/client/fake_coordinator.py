"""A scripted coordinator that stands in for `ssh <target> -- <remote_bin> rpc ...`.

Tests point `common.ssh.SSH_BINARY` at a wrapper that runs this file. It never contacts a
host. Behaviour comes from `$FAKE_DIR/scenario.json`; every request line it receives is
appended to `$FAKE_DIR/requests.jsonl`, an upload is saved as `$FAKE_DIR/upload.tar.gz`,
and the ssh argv is saved as `$FAKE_DIR/argv.json`.

Scenario keys: `down` (exit 255 like a failed ssh connection), `submit_state`, `log`
(list of strings), `outcome`, `exit_code`, `delay_s` (between watch messages),
`drop_watch_once` (first watch exits 255 after the first log chunk), `error` (reply
`error` with this code to every request), `jobs` (for queue), `status_state`.
"""

import hashlib
import json
import os
import shlex
import sys
import threading
import time

DIR = os.environ["FAKE_DIR"]


def load(name, default):
    try:
        with open(os.path.join(DIR, name)) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


def record(line):
    with open(os.path.join(DIR, "requests.jsonl"), "a") as fh:
        fh.write(line.decode().rstrip("\n") + "\n")


def send(kind, request_id, **body):
    line = {"body": body, "request_id": request_id, "type": kind, "v": 1}
    sys.stdout.write(json.dumps(line, sort_keys=True) + "\n")
    sys.stdout.flush()


def main():
    args = sys.argv[1:]
    with open(os.path.join(DIR, "argv.json"), "w") as fh:
        json.dump(args, fh)
    scenario = load("scenario.json", {})
    if scenario.get("down"):
        sys.stderr.write("ssh: connect to host build-1 port 22: Connection refused\n")
        return 255
    command = shlex.split(args[args.index("--") + 1])
    if command[1] == "rpc-upload":
        data = sys.stdin.buffer.read()
        with open(os.path.join(DIR, "upload.tar.gz"), "wb") as fh:
            fh.write(data)
        ok = hashlib.sha256(data).hexdigest() == command[3]
        if not ok:
            send("error", "upload", code="bad_request", message="sha256 mismatch")
            return 1
        send("status_ok", "upload", job_id=command[2], state="queued", position=1)
        return 0
    line = sys.stdin.buffer.readline()
    record(line)
    msg = json.loads(line)
    rid, body, kind = msg["request_id"], msg["body"], msg["type"]
    if scenario.get("error"):
        send("error", rid, code=scenario["error"], message="scripted failure")
        return 1
    if kind == "submit":
        send("submit_ok", rid, job_id="job-01JC3X0000000000000000ABCD",
             state=scenario.get("submit_state", "uploading"))
    elif kind == "watch":
        return watch(scenario, rid, body)
    elif kind == "queue":
        send("queue_ok", rid, jobs=scenario.get("jobs", []))
    elif kind == "logs":
        text = "".join(scenario.get("log", []))
        data = text.encode()[body["offset"]:].decode()
        send("log_chunk", rid, job_id=body["job_id"], offset=body["offset"], data=data, eof=True,
             next_offset=body["offset"] + len(data.encode()))
    else:  # status, cancel
        send("status_ok", rid, job_id=body["job_id"], state=scenario.get("status_state", "queued"),
             outcome=scenario.get("outcome", "cancelled"), exit_code=scenario.get("exit_code"),
             log_size=scenario.get("log_size", 0))
    return 0


def watch(scenario, rid, body):
    threading.Thread(target=lambda: [record(ln) for ln in sys.stdin.buffer], daemon=True).start()
    delay = scenario.get("delay_s", 0)
    job_id = body["job_id"]
    send("status_ok", rid, job_id=job_id, state="queued", position=2)
    send("status_ok", rid, job_id=job_id, state="running", worker="build-1")
    offset = 0
    dropped = os.path.join(DIR, "dropped")
    for chunk in scenario.get("log", []):
        time.sleep(delay)
        size = len(chunk.encode())
        if offset + size > body["offset"]:
            send("log_chunk", rid, job_id=job_id, offset=offset, data=chunk)
        offset += size
        if scenario.get("drop_watch_once") and not os.path.exists(dropped):
            open(dropped, "w").close()
            return 255
    time.sleep(delay)
    send("result", rid, job_id=job_id, outcome=scenario.get("outcome", "passed"),
         exit_code=scenario.get("exit_code", 0), duration_s=12.5)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)  # the watch stdin reader is a daemon thread
