"""A drill against a real Docker daemon: what mulebox generates really is what cleanup finds.

The test suite uses a fake Docker on purpose, so it cannot show that a generated compose
file produces labelled resources. This does: it prepares a job the way the worker does,
starts it, checks what Docker made of it, and removes it with the worker's own teardown.
It needs a machine with Docker and an image that is already there, and pulls nothing else.

It only ever removes what carries the labels of a job id it just made up, and says what
those are first. Run it on a node from a checkout, or from here without one:

    ssh build-1 '~/.mulebox/venv/bin/python - --real-docker' < tools/drill_compose.py
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from mulebox.common import compose
from mulebox.common.compose import ComposeError
from mulebox.common.ids import new_id
from mulebox.worker import compose_job, docker_cleanup, jobspec
from mulebox.worker.docker import Docker
from mulebox.worker.ports import PortPool

WORKER = "mulebox-drill"
COMPOSE = """
services:
  cache:
    image: {image}
    ports: ["6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 1s
      retries: 30
  app:
    build: .
    image: example-app:drill
    command: ["sleep", "600"]
    volumes:
      - data:/data
      - .:/app
      - {outside}:/seed:ro
    depends_on:
      cache:
        condition: service_healthy
  second:
    image: example-app:drill
    command: ["sleep", "600"]
    depends_on: [app]
volumes:
  data:
"""
KINDS = {"containers": ("ps", "--all", "--format", "{{.Names}}"),
         "networks": ("network", "ls", "--format", "{{.Name}}"),
         "volumes": ("volume", "ls", "--format", "{{.Name}}"),
         "images": ("image", "ls", "--format", "{{.Repository}}:{{.Tag}}")}


class Drill:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, passed: bool, what: str) -> None:
        print(f"{'ok  ' if passed else 'FAIL'} {what}")
        self.failed += 0 if passed else 1


def labelled(docker: Docker, job_id: str) -> dict[str, list[str]]:
    return {kind: docker.lines(*args, "--filter", compose.job_filter(job_id))
            for kind, args in KINDS.items()}


def prepare(docker: Docker, job_id: str, src: Path) -> dict[str, str]:
    def environment(extra: dict[str, str]) -> dict[str, str]:
        return jobspec.build_env(job_id, [], extra=extra)

    job = compose_job.prepare(docker, PortPool(), job_id, WORKER, "docker-compose.yml", src, {},
                              environment)
    for note in job.notes:
        print(f"note {note}")
    return {**os.environ, **environment(job.extra_env)}


def check_running(drill: Drill, docker: Docker, job_id: str, env: dict[str, str],
                  src: Path) -> None:
    found = labelled(docker, job_id)
    print(f"list what teardown will remove: {json.dumps(found)}")
    project = compose.project_name(job_id)
    drill.check(len(found["containers"]) == 3, "three containers carry the job's label")
    drill.check(found["networks"] == [f"{project}_default"], "the network is the job's own")
    drill.check(found["volumes"] == [f"{project}_data"], "the volume is the job's own")
    drill.check(len(found["images"]) == 1
                and compose.owns_image(job_id, found["images"][0]),
                "the built image has one tag, and it is the job's")
    drill.check(job_id in docker_cleanup.labelled_jobs(docker, WORKER),
                "a crash recovery would find this job")
    published = docker.lines("ps", "--filter", compose.job_filter(job_id), "--format", "{{.Ports}}")
    drill.check(any("127.0.0.1:" in line for line in published)
                and not any("0.0.0.0:" in line for line in published),
                "the published port is on 127.0.0.1 only")
    reply = docker.run("compose", "exec", "-T", "app", "redis-cli", "-h", "cache", "ping",
                       env=env, cwd=src)
    drill.check(reply.strip() == "PONG", "a service reaches another by name over the job's network")
    second = docker.lines("compose", "exec", "-T", "second", "cat", "/built-here",
                          env=env, cwd=src)
    drill.check(second == ["built"], "a service using the built image's tag got the job's build")


def check_gone(drill: Drill, docker: Docker, job_id: str, image: str) -> None:
    found = labelled(docker, job_id)
    drill.check(not any(found.values()), f"nothing is left of the job: {json.dumps(found)}")
    drill.check(not docker.lines("image", "ls", "--format", "{{.ID}}", "example-app:drill"),
                "the project's own tag was never created")
    drill.check(bool(docker.lines("image", "ls", "--format", "{{.ID}}", image)),
                "the base image stayed")


def check_missing_source(drill: Drill, docker: Docker, root: Path, src: Path) -> None:
    missing = root / "missing-source"
    text = (src / "docker-compose.yml").read_text()
    (src / "docker-compose.yml").write_text(f"services:\n  app:\n    image: x\n    volumes:\n"
                                            f"      - {missing}:/m:ro\n")
    try:
        prepare(docker, new_id("job"), src)
        drill.check(False, "a missing outside source is refused")
    except ComposeError as exc:
        drill.check("does not exist" in str(exc), "a missing outside source is refused")
    drill.check(not missing.exists(), "and it was not created")
    (src / "docker-compose.yml").write_text(text)


def run(image: str) -> int:
    drill, docker, job_id = Drill(), Docker(), new_id("job")
    print(f"job {job_id}")
    with tempfile.TemporaryDirectory(prefix="mulebox-drill-") as folder:
        root = Path(folder)
        src, outside = root / "src", root / "outside"
        src.mkdir()
        outside.mkdir()
        (src / "Dockerfile").write_text(f"FROM {image}\nRUN echo built > /built-here\n")
        (src / "docker-compose.yml").write_text(COMPOSE.format(image=image, outside=outside))
        env = prepare(docker, job_id, src)
        model = json.loads((root / compose_job.GENERATED_FILE).read_text())
        binds = [v for v in model["services"]["app"]["volumes"] if v["target"] == "/seed"]
        drill.check(binds[0]["bind"]["create_host_path"] is False,
                    "an outside read-only bind cannot create its source")
        try:
            docker.run("compose", "up", "--detach", "--wait", env=env, cwd=src, timeout_s=120.0)
            check_running(drill, docker, job_id, env, src)
        finally:
            docker_cleanup.teardown(docker, job_id)
        check_gone(drill, docker, job_id, image)
        check_missing_source(drill, docker, root, src)
    print("drill failed" if drill.failed else "drill passed")
    return 1 if drill.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--real-docker", action="store_true",
                        help="confirm: this starts and removes containers on this machine")
    parser.add_argument("--image", default="redis:7-alpine",
                        help="an image already on this machine with redis-cli (default: %(default)s)")
    args = parser.parse_args()
    if not args.real_docker:
        parser.error("this talks to a real Docker daemon; pass --real-docker to mean it")
    return run(args.image)


if __name__ == "__main__":
    raise SystemExit(main())
