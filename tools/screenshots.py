"""The README's screenshots, from the dashboard's stand-in data (web/dev, `npm run dev`).

Starts the stand-in with Vite, drives headless Chrome over the DevTools protocol (aiohttp is
already a dependency) and writes PNGs to docs/images/. Every name in them is made up by
web/dev/fixtures.ts, so no real machine, project or address can reach a picture. Run from a
checkout with web/node_modules installed:

    .venv/bin/python tools/screenshots.py            # every shot
    .venv/bin/python tools/screenshots.py queue-dark # only the named ones
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "images"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SCALE = 1.5


@dataclass
class Shot:
    name: str
    route: str                      # the dashboard's hash route, or a file under docs/
    theme: str = "dark"
    width: int = 1440
    height: int = 900
    env: dict[str, str] = field(default_factory=dict)
    prefs: dict[str, str] = field(default_factory=dict)
    script: str = ""                # run once the page has its data
    wait: float = 4.0


CLEAN = {"MULEBOX_MOCK_CLEAN": "1"}
SHOTS = [
    Shot("queue-dark", "#/", env=CLEAN),
    Shot("queue-light", "#/", "light", env=CLEAN),
    Shot("job-dark", "job:running-agent", env=CLEAN),
    Shot("ci-run-light", "job:running-runner", "light", env=CLEAN),
    Shot("history-light", "#/history", "light", env=CLEAN),
    Shot("statistics-dark", "#/stats", env=CLEAN),
    Shot("machines-dark", "#/machines", env={**CLEAN, "MULEBOX_MOCK_MACHINES": "5"}),
    Shot("cpu-compact-light", "#/", "light", env={**CLEAN, "MULEBOX_MOCK_CORES": "32"},
         prefs={"mulebox-cpu-view": "compact"}),
    Shot("phone-dark", "#/", width=390, height=844, env=CLEAN),
    Shot("node-settings-dark", "#/", env=CLEAN,
         script="document.querySelector('[aria-label=\"Settings of build-1\"]').click()"),
    Shot("order-light", "#/", "light", height=1700, env={**CLEAN, "MULEBOX_MOCK_SCENE": "order"},
         script="[...document.querySelectorAll('button')].find(b => b.textContent.startsWith('Order')).click()"),
    Shot("downloads-dark", "#/", height=700, env={**CLEAN, "MULEBOX_MOCK_SCENE": "downloads"},
         script="[...document.querySelectorAll('h1,h2,h3')].find(h => h.textContent.trim() === 'Jobs')"
                "?.scrollIntoView(); window.scrollBy(0, -88)"),
    Shot("sign-in-light", "page:login.html", "light", width=1000, height=640, env=CLEAN, wait=2.0),
    Shot("sign-in-dark", "page:login.html", width=1000, height=640, env=CLEAN, wait=2.0),
    Shot("design-system-light", "file:design-system/specimen.html", "light", height=1100, wait=2.0,
         script="document.documentElement.dataset.theme === 'dark' && document.getElementById('theme-toggle').click()"),
]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_vite(env: dict[str, str]) -> tuple[subprocess.Popen, str]:
    port = free_port()
    proc = subprocess.Popen(["npx", "vite", "--host", "127.0.0.1", "--port", str(port), "--strictPort"], cwd=ROOT / "web",
                            env={**os.environ, **env}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/app/"
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return proc, url
        except OSError:
            time.sleep(0.25)
    proc.terminate()
    raise SystemExit("the stand-in did not start; is web/node_modules installed?")


class Page:
    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self.ws, self.next_id = ws, 0

    async def send(self, method: str, **params):
        self.next_id += 1
        await self.ws.send_json({"id": self.next_id, "method": method, "params": params})
        async for msg in self.ws:
            body = json.loads(msg.data)
            if body.get("id") == self.next_id:
                if "error" in body:
                    raise RuntimeError(f"{method}: {body['error']}")
                return body.get("result", {})
        raise RuntimeError("the browser closed the connection")

    async def eval(self, expression: str):
        result = await self.send("Runtime.evaluate", expression=expression, awaitPromise=True,
                                 returnByValue=True)
        return result.get("result", {}).get("value")


async def job_route(base: str, which: str) -> str:
    """`#/job/<id>` of the first running job of a kind (agent or runner) in the stand-in."""
    kind = {"running-agent": "job", "running-runner": "runner"}[which]
    async with aiohttp.ClientSession() as http, http.get(base.split("/app/")[0] + "/api/queue") as reply:
        queue = await reply.json()
    row = next(r for r in queue["running"] if r.get("kind", "job") == kind)
    return f"#/job/{row['job_id']}"


async def take(page: Page, shot: Shot, base: str | None) -> None:
    mobile = shot.width < 520
    await page.send("Emulation.setDeviceMetricsOverride", width=shot.width, height=shot.height,
                    deviceScaleFactor=SCALE, mobile=mobile)
    await page.send("Emulation.setEmulatedMedia",
                    features=[{"name": "prefers-color-scheme", "value": shot.theme}])
    if shot.route.startswith("file:"):
        await page.send("Page.navigate", url=(ROOT / "docs" / shot.route[5:]).as_uri())
        await asyncio.sleep(1)
    elif shot.route.startswith("page:"):
        await page.send("Page.navigate", url=base + shot.route[5:])
    else:
        route = await job_route(base, shot.route[4:]) if shot.route.startswith("job:") else shot.route
        await page.send("Page.navigate", url=base)
        await asyncio.sleep(1)
        stored = {"mulebox-theme": shot.theme, **shot.prefs}
        await page.eval("localStorage.clear();" + "".join(
            f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)});" for k, v in stored.items()))
        await page.send("Page.reload", ignoreCache=True)  # the stored theme and views apply on load
        await asyncio.sleep(1.5)
        await page.eval(f"location.hash = {json.dumps(route)}")
    await asyncio.sleep(shot.wait)
    if shot.script:
        await page.eval(shot.script)
        await asyncio.sleep(1)
    image = await page.send("Page.captureScreenshot", format="png")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{shot.name}.png").write_bytes(base64.b64decode(image["data"]))
    print(f"docs/images/{shot.name}.png")


async def main(names: list[str]) -> None:
    shots = [s for s in SHOTS if not names or s.name in names]
    port = free_port()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}",
                                   f"--user-data-dir={profile}", "--hide-scrollbars", "--no-first-run",
                                   "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        servers: dict[str, tuple[subprocess.Popen, str]] = {}
        try:
            async with aiohttp.ClientSession() as http:
                for _ in range(40):
                    try:
                        async with http.get(f"http://127.0.0.1:{port}/json/list") as reply:
                            target = next(t for t in await reply.json() if t["type"] == "page")
                        break
                    except (aiohttp.ClientError, StopIteration):
                        await asyncio.sleep(0.25)
                else:
                    raise SystemExit(f"Chrome did not start ({CHROME}); set CHROME to its path")
                async with http.ws_connect(target["webSocketDebuggerUrl"], max_msg_size=0) as ws:
                    page = Page(ws)
                    for shot in shots:
                        base = None
                        if not shot.route.startswith("file:"):
                            key = json.dumps(shot.env, sort_keys=True)
                            if key not in servers:
                                servers[key] = start_vite(shot.env)
                            base = servers[key][1]
                        await take(page, shot, base)
        finally:
            for proc, _ in servers.values():
                proc.terminate()
            chrome.terminate()
            chrome.wait(10)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
