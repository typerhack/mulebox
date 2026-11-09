"""The worker's service: recover what a last run left, then the claim loop."""

from __future__ import annotations

import threading

from mulebox.common.config import NodeConfig
from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.redact import StreamRedactor, secret_values
from mulebox.runners.runner_meter import CiContainers, RunnerMeter
from mulebox.runners.supervise import Supervisor
from mulebox.worker.agent import Agent
from mulebox.worker.docker import Docker
from mulebox.worker.executor import Executor
from mulebox.worker.link import CoordinatorLink
from mulebox.worker.paths import NodePaths

LOG = get_logger("worker.serve")


def serve(node: NodeConfig, link: CoordinatorLink, executor: Executor, *,
          paths: NodePaths | None = None, stop: threading.Event | None = None,
          docker: Docker | None = None) -> None:
    """Recovery first, then the claim loop until `stop` is set."""
    paths = paths or NodePaths.from_config(node.roots)
    stop = stop or threading.Event()
    agent = Agent(node, link, executor, paths, docker=docker,
                  supervisor=Supervisor(node.name, paths.runners, redactor=lambda: StreamRedactor(
                      secret_values(node.job_env)), meter=RunnerMeter(
                          containers=CiContainers(paths.runners, docker))))
    agent.recover()
    LOG.info("worker %s ready (%d slot(s))", node.name, node.slots)
    while not stop.is_set():
        try:
            agent.step()
        except (MuleboxError, OSError) as exc:
            LOG.error("worker step failed: %s", exc)
        stop.wait(agent.wait_s())
    agent.shutdown()
