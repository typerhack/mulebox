"""An isolated runner: one fresh, confined container per GitHub job (design.md, Runners for
public repositories).

A place is a folder `<runners>/<name>/` whose `.mulebox-runner.json` says `isolated`. The
worker keeps one thread per place (place_keeper.py), which loops:

1. the image (place_image.py), built once per runner version;
2. a one-job runner from GitHub (jit.py), its configuration on the container's stdin;
3. a container from that image (place_container.py): no folder of the node but the place's
   `hooks` (read-only), this round's own `io-<id>` and `_diag`, no Docker socket, no
   capabilities, no new privileges, a network of its own, limits on memory and processes;
4. the job's hook asks through `io-<id>`; the node runs the guard and reserves the slot
   (place_bridge.py) in a thread of its own, as the slot can take a while. Each round has its
   own `io` folder, so an answer meant for one job can never reach the next;
5. whatever happened, the round ends the same way: the container is removed (also when only
   its `docker` client died), a decision still in flight is given up and waited for, the slot
   is released with the job's result from its diary (hooks.completed), and a runner that never
   got a job is deleted from GitHub. Then again, after a pause when something failed.

A worker that stops leaves a container whose job has begun, or may have, running, and the next
worker takes it over and ends its round (place_handover.py), so a deploy strands no job.

What the container wrote is owned by its user, not the node's, so before a folder of it is
deleted the node takes it back (worker/reclaim.py). `.mulebox-place` in the folder names the
running container, for supervision (supervise.py). A place whose metadata says `removing`
starts no new round (place_manage.remove_isolated).
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from mulebox.common.errors import MuleboxError
from mulebox.common.ids import new_ulid
from mulebox.common.log import get_logger
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.runners import guard, hooks, jit, layout, place_bridge, place_container
from mulebox.runners import place_handover, place_hook, place_image, release
from mulebox.runners.github import GhRun, run_gh
from mulebox.runners.supervise import PLACE_MARKER as MARKER
from mulebox.runners.supervise import PLACE_ROUND as ROUND
from mulebox.worker import reclaim
from mulebox.worker.docker import Docker
from mulebox.worker.link import CoordinatorLink
from mulebox.worker.paths import NodePaths

LOG = get_logger("runners.place")
POLL_S = 0.5
PAUSE_S = (10.0, 30.0, 120.0, 300.0)  # after a failed round, growing
VERSION_EVERY_S = 24 * 3600.0
DECIDE_WAIT_S = 30.0  # a coordinator call in flight when the container ended
IO_PREFIX = "io-"


def latest_version() -> str:
    return release.latest_release(None).version


class Place:
    def __init__(self, folder: Path, worker: str, link: CoordinatorLink, paths: NodePaths, *,
                 stop: threading.Event, docker: Docker | None = None, gh: GhRun = run_gh,
                 version: Any = latest_version, popen: Any = subprocess.Popen) -> None:
        self.folder, self.worker, self.link, self.paths = folder, worker, link, paths
        self.stop, self.docker, self.gh = stop, docker or Docker(), gh
        self.version_of, self.popen = version, popen
        self._version: tuple[float, str] | None = None
        self.handed_over = False  # this round's container is left running for the next worker

    @property
    def name(self) -> str:
        return self.folder.name

    def run(self) -> None:
        """Rounds until stopped; a failed round waits longer each time, up to 5 minutes."""
        failures = 0
        while not self.stop.is_set():
            try:
                self.round()
                failures = 0
            except Exception as exc:  # noqa: BLE001 - a place must outlive any one failure
                LOG.error("isolated runner %s: %s", self.name, exc)
                self.stop.wait(PAUSE_S[min(failures, len(PAUSE_S) - 1)])
                failures += 1

    def version(self) -> str:
        """The newest runner release, asked of GitHub once a day."""
        now = time.monotonic()
        if self._version is None or now - self._version[0] > VERSION_EVERY_S:
            self._version = (now, self.version_of())
        return self._version[1]

    def _remove(self, path: Path) -> None:
        """Delete a folder the container wrote in, taking the place's folder back first when
        needed: through the folder above it, the node's own, as the container may have made
        the one it got unreadable."""
        try:
            remove_tree(path, self.paths.roots)
        except (MuleboxError, OSError):
            reclaim.reclaim_runner_dir(self.docker, self.paths, self.folder, self.worker)
            remove_tree(path, self.paths.roots)

    def _fresh(self, path: Path) -> Path:
        self._remove(path)
        ensure_dir(path, self.paths.roots)
        os.chmod(path, 0o777)  # the container's user writes here; the folder above is the node's
        return path

    def _left_over(self) -> None:
        """What an earlier round, or a worker that stopped, left: containers, io folders."""
        place_container.remove_left(self.docker, self.name)
        for entry in sorted(self.folder.iterdir()):
            if entry.name.startswith(IO_PREFIX) and not entry.is_symlink():
                self._remove(entry)

    def _meta(self) -> dict[str, Any]:
        meta = guard.runner_meta(self.folder) or {}
        if not meta.get("isolated") or not meta.get("repo") or meta.get("removing"):
            raise place_container.PlaceError(
                "its .mulebox-runner.json is not a running isolated runner's")
        return meta

    def round(self) -> None:
        """One container, one job (or none, when stopped first). `.mulebox-round` lasts as
        long as the round, written before the metadata is read, so `runner remove` can wait
        for it (place_manage.py)."""
        layout.write_file(self.paths, self.folder / ROUND, f"{os.getpid()}\n")
        try:
            self._round()
        finally:
            _quietly(lambda: remove_tree(self.folder / ROUND, self.paths.roots), "round mark")

    def _round(self) -> None:
        meta = self._meta()
        self.handed_over = False
        if self._take_over(meta):
            return
        self._left_over()
        self._release_left()
        image = place_image.ensure(self.docker, self.paths, self.version())
        place_container.ensure_network(self.docker)
        hooks_dir = place_hook.write_hooks(self.paths, self.folder)
        suffix = new_ulid()[-8:].lower()
        io_dir = self._fresh(self.folder / f"{IO_PREFIX}{suffix}")
        diag = self._fresh(self.folder / "_diag")
        container = place_handover.container_name(self.name, suffix)
        runner: jit.JitRunner | None = None
        asked = False
        meta = self._meta()  # once more: the image can take minutes, and removal may have begun
        try:
            runner = jit.create(meta["repo"], jit.runner_name(self.name, suffix),
                                [jit.arch_label(), *(meta.get("labels") or ())], self.gh)
            layout.write_file(self.paths, self.folder / MARKER, container + "\n")
            argv = place_container.run_argv(container, self.name, image, hooks_dir=hooks_dir,
                                            io_dir=io_dir, diag_dir=diag)
            asked = self._start_and_watch(argv, runner, container, io_dir, meta["repo"])
        finally:
            if not self.handed_over:
                self._end_round(meta["repo"], container,
                                [runner.id] if runner is not None and not asked else None)

    def _end_round(self, repo: str, container: str, unused: list[int] | None) -> None:
        """Each step on its own: one failing must not skip the others. `unused`: the ids of
        one-job runners that never got their job, None to ask GitHub for this place's."""
        _quietly(lambda: place_container.remove(self.docker, container), "container")
        _quietly(lambda: self._delete_unused(repo, unused), "one-job runner")
        _quietly(self._release_left, "slot")
        _quietly(lambda: remove_tree(self.folder / MARKER, self.paths.roots), "marker")

    def _take_over(self, meta: dict[str, Any]) -> bool:
        """Follow a container an earlier worker left running to its end; False if none."""
        found = place_handover.held(self.docker, self.name, self.folder, IO_PREFIX)
        if found is None:
            return False
        container, io_dir = found
        LOG.info("isolated runner %s: taking over %s from the last worker", self.name, container)
        asked = False
        try:
            asked = self._watch(place_handover.Held(self.docker, container), container, io_dir,
                                meta["repo"], None)
        finally:
            if not self.handed_over:
                self._end_round(meta["repo"], container, None if not asked else [])
        return True

    def _delete_unused(self, repo: str, ids: list[int] | None) -> None:
        for runner_id in jit.ids_of(repo, self.name, self.gh) if ids is None else ids:
            if not jit.delete(repo, runner_id, self.gh):
                LOG.warning("isolated runner %s: GitHub kept unused runner %s", self.name,
                            runner_id)

    def _start_and_watch(self, argv: list[str], runner: jit.JitRunner, container: str,
                         io_dir: Path, repo: str) -> bool:
        with open(self.folder / "container.log", "wb") as log:
            proc = self.popen(argv, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
            try:
                proc.stdin.write((runner.config + "\n").encode())
                proc.stdin.close()
                return self._watch(proc, container, io_dir, repo, [runner.id])
            finally:
                if proc.poll() is None and not self.handed_over:
                    place_container.remove(self.docker, container)
                    try:
                        proc.wait(timeout=60)
                    except subprocess.TimeoutExpired:
                        proc.kill()

    def _watch(self, proc: Any, container: str, io_dir: Path, repo: str,
               runner_ids: list[int] | None) -> bool:
        """Wait for the container to end, answering its hook once; True if a job asked.

        The container counts as running while its `docker` client does or Docker says it
        does, as the client can die alone (the worker's stop signal reaches it too). A slot
        still being waited for when the container ends is given up (`gone`) and waited for, or
        it would be granted later and held by the next container, which has no job. When the
        worker stops, a container whose job has begun, or may have, is left to the next worker
        (place_handover.py), and a decision in flight is left unanswered for it."""
        decide: threading.Thread | None = None
        gone = threading.Event()
        answered = (io_dir / place_hook.ANSWER).exists()  # by an earlier worker
        try:
            while proc.poll() is None or place_container.running(self.docker, container):
                if self.stop.is_set():
                    if place_handover.keep_on_stop(repo, self.name, io_dir, runner_ids,
                                                   self.gh):
                        self.handed_over = True
                        LOG.info("isolated runner %s: %s left running for the next worker",
                                 self.name, container)
                        break
                    place_container.remove(self.docker, container)
                    proc.wait(timeout=60)
                    break
                if decide is None and not answered:
                    request = place_bridge.read_request(io_dir)
                    if request is not None:
                        decide = threading.Thread(target=self._decide,
                                                  args=(request, io_dir, gone),
                                                  name=f"place-{self.name}", daemon=True)
                        decide.start()
                self.stop.wait(POLL_S)
        finally:
            gone.set()
            while decide is not None and decide.is_alive():
                decide.join(timeout=DECIDE_WAIT_S)
                if decide.is_alive():
                    LOG.warning("isolated runner %s: still deciding on its last job", self.name)
        return answered or decide is not None

    def _decide(self, request: dict[str, str], io_dir: Path, gone: threading.Event) -> None:
        def sleep(seconds: float) -> None:
            if gone.wait(seconds):
                raise place_container.PlaceError("its container ended before it got a slot")

        def reserve(env: Any, worker: str, link: Any, paths: Any, *, out: Any) -> int:
            return hooks.started(env, worker, link, paths, sleep=sleep, out=out)

        try:
            ok, message = place_bridge.handle(request, folder=self.folder, io_dir=io_dir,
                                              worker=self.worker, link=self.link,
                                              paths=self.paths, reserve=reserve)
        except Exception as exc:  # noqa: BLE001 - the job must get an answer, a refusal
            ok, message = False, f"mulebox: the node could not decide on this job: {exc}"
        if self.handed_over:
            return  # the next worker decides on it again, with the same reservation key
        if gone.is_set():
            ok = False  # its container is gone: nothing may be allowed after it
        try:
            place_bridge.answer(self.paths, io_dir, ok, message)
        except (MuleboxError, OSError) as exc:
            LOG.warning("isolated runner %s: could not answer its job: %s", self.name, exc)

    def _release_left(self) -> None:
        """Release a reservation this place still holds (its job ended, or the worker did)."""
        hooks.completed({"RUNNER_NAME": self.name}, self.link, self.paths,
                        out=_Quiet())


def _quietly(step: Any, what: str) -> None:
    try:
        step()
    except Exception as exc:  # noqa: BLE001 - logged; the round's other cleanup goes on
        LOG.warning("isolated runner cleanup (%s) failed: %s", what, exc)


class _Quiet:
    def write(self, text: str) -> int:
        if text.strip():
            LOG.info("%s", text.strip())
        return len(text)

    def flush(self) -> None:
        pass
