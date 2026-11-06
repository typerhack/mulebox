import asyncio
import json
import re

import pytest

from mulebox.dashboard import streams
from mulebox.dashboard.server import STATIC_DIR, host_name
from mulebox.version import get_version

from .conftest import NOW


def sse(text):
    """[(event, data)] of an SSE body."""
    found = []
    for block in text.split("\n\n"):
        event = re.search(r"^event: (.+)$", block, re.M)
        data = re.search(r"^data: (.+)$", block, re.M)
        if event:
            found.append((event[1], json.loads(data[1])))
    return found


@pytest.mark.parametrize("host, name", [("127.0.0.1:8090", "127.0.0.1"), ("LOCALHOST", "localhost"),
                                        ("[::1]:8090", "[::1]"), (None, "")])
def test_host_name(host, name):
    assert host_name(host) == name


def test_other_hosts_are_refused_for_dns_rebinding(call):
    async def go(client):
        reply = await client.get("/api/queue", headers={"Host": "evil.example:8090"})
        return reply.status
    assert call(go) == 421


def test_security_headers_on_every_reply(call):
    async def go(client):
        pages = [await client.get("/"), await client.get("/api/queue"),
                 await client.get("/nothing-here")]
        return [(r.status, r.headers) for r in pages]
    results = call(go)
    assert [status for status, _ in results] == [200, 200, 404]
    for _, headers in results:
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert "unsafe" not in headers["Content-Security-Policy"]
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"
    assert results[1][1]["Cache-Control"] == "no-store"
    assert results[0][1]["Cache-Control"] == "no-cache"  # the page must follow an upgrade


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_the_server_is_read_only(call, run_job, method):
    job_id, _ = run_job()

    async def go(client):
        reply = await getattr(client, method)(f"/api/jobs/{job_id}")
        return reply.status
    assert call(go) == 405


def test_health_and_queue(call, run_job):
    job_id, _ = run_job()

    async def go(client):
        return await (await client.get("/healthz")).json(), await (await client.get("/api/queue")).json()
    health, queue = call(go)
    assert health == {"ok": True, "version": get_version(), "lan": False,
                      "sign_in": False}
    assert queue["running"][0]["job_id"] == job_id


def test_a_new_viewer_gets_elapsed_times_of_now_not_of_the_last_event(data, hub, run_job, tmp_path):
    """The last published queue event is minutes old once nothing changes; a viewer that
    connects then must not tick on from its stale elapsed times."""
    from aiohttp.test_utils import TestClient, TestServer

    from mulebox.dashboard.server import build_app
    run_job()
    asyncio.run(hub.queue_step())  # published at NOW

    async def go():
        app = build_app(data, hub, clock=lambda: NOW + 600, start_hub=False, static_dir=tmp_path)
        async with TestClient(TestServer(app)) as client:
            reply = await client.get("/api/events")
            text = (await reply.content.read(4096)).decode()
            reply.close()
            return text
    queue = next(d for e, d in sse(asyncio.run(go())) if e == "queue")
    assert queue["running"][0]["elapsed_s"] == 600.0
    assert hub.current_queue()["running"][0]["elapsed_s"] == 0.0


def test_job_and_history_errors(call):
    async def go(client):
        return [(await client.get(url)).status for url in (
            "/api/jobs/nope", "/api/jobs/nope/log", "/api/jobs/nope/log.txt",
            "/api/history?limit=x", "/api/history?before=x")]
    assert call(go) == [404, 404, 404, 400, 400]


def test_events_start_with_a_snapshot_then_replay_by_id(call, hub):
    first = hub.bus.publish("queue", {"running": [], "n": 1})
    hub.bus.publish("metrics", {"t": NOW})
    hub.history.append({"t": NOW})

    async def go(client):
        fresh = await client.get("/api/events")
        chunk = b""
        while chunk.count(b"event:") < 3:  # the stream may arrive in more than one read
            chunk += await asyncio.wait_for(fresh.content.read(4096), 5)
        fresh.close()
        resumed = await client.get("/api/events", headers={"Last-Event-ID": first.id})
        again = await resumed.content.read(4096)
        resumed.close()
        return fresh.headers["Content-Type"], chunk.decode(), again.decode()
    kind, snapshot, replay = call(go)
    assert kind == "text/event-stream"
    assert [event for event, _ in sse(snapshot)] == ["queue", "machines", "metrics_history"]
    assert sse(replay) == [("metrics", {"t": NOW})]


def test_log_stream_of_a_finished_job_ends(call, run_job, write_log, finish_job):
    job_id, state = run_job()
    write_log(state, "<script>one</script>\n")
    finish_job(state)

    async def go(client):
        return await (await client.get(f"/api/jobs/{job_id}/log")).text()
    events = sse(call(go))
    assert [e for e, _ in events] == ["state", "log", "end"]
    assert events[1][1]["data"] == "<script>one</script>\n"  # text; the page never parses it
    assert events[2][1]["outcome"] == "passed"


def test_a_quiet_log_stream_sends_a_beat_a_page_can_see(call, run_job, monkeypatch):
    job_id, _ = run_job()
    monkeypatch.setattr(streams, "BEAT_S", 0.0)

    async def go(client):
        reply = await client.get(f"/api/jobs/{job_id}/log")
        text = b""
        while b"event: beat" not in text:
            text += await asyncio.wait_for(reply.content.readany(), 5)
        reply.close()
        return text.decode()
    assert ("beat", {}) in sse(call(go))


def test_log_stream_resumes_at_a_byte_offset_and_bad_offsets_are_ignored(
        call, run_job, write_log, finish_job):
    job_id, state = run_job()
    write_log(state, "abcdef")
    finish_job(state)

    async def go(client):
        url = f"/api/jobs/{job_id}/log"
        return [await (await client.get(url, headers=headers)).text() for headers in (
            {"Last-Event-ID": "4"}, {"Last-Event-ID": "²".encode().decode("latin-1")})]
    resumed, bad = call(go)
    assert [d["data"] for e, d in sse(resumed) if e == "log"] == ["ef"]
    assert [d["data"] for e, d in sse(bad) if e == "log"] == ["abcdef"]


def test_log_text_and_tail(call, run_job, write_log, finish_job):
    job_id, state = run_job()
    write_log(state, "abcdef")
    finish_job(state)

    async def go(client):
        text = await client.get(f"/api/jobs/{job_id}/log.txt")
        tail = await client.get(f"/api/jobs/{job_id}/log?tail=2")
        return text.headers["Content-Type"], await text.text(), await tail.text()
    kind, body, tail = call(go)
    assert kind.startswith("text/plain") and body == "abcdef"
    assert [d["data"] for e, d in sse(tail) if e == "log"] == ["ef"]


def test_the_shipped_page_works_under_the_policy():
    page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "style=" not in page and "onclick" not in page.lower()
    assert not re.search(r"<script(?![^>]*\bsrc=)", page)  # no inline script
    assert "http://" not in page and "https://" not in page  # no CDN
    for name in ("app.js", "style.css", "charts.js", "jobs.js", "lanes.js", "jobdetail.js",
                 "machine.js", "machines.js", "format.js", "canceljob.js", "canceljob.css"):
        assert (STATIC_DIR / name).is_file()
    # Filter lists block some names outright, and one blocked module blanks the page.
    assert not (STATIC_DIR / "logview.js").exists()
    assert "Loading" in page  # what a viewer sees if the scripts never run
    code = "".join(p.read_text(encoding="utf-8") for p in STATIC_DIR.glob("*.js"))
    assert "innerHTML" not in code and "insertAdjacentHTML" not in code and "eval(" not in code
