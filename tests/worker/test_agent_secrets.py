"""A secret in the machine's settings stays out of what a job's log stores."""

from dataclasses import replace

from mulebox.common.protocol import MessageType
from mulebox.worker.agent import Agent

from .test_agent import clock, executor, run_until, submit  # noqa: F401


def test_a_secret_of_the_machine_never_reaches_the_log(node, fake_link, executor, paths,  # noqa: F811
                                                       clock):  # noqa: F811
    env = {"NPM_TOKEN": "fake-machine-value", "NODE_OPTIONS": "--max-old-space-size=4096"}
    worker = Agent(replace(node, job_env=env), fake_link, executor, paths, clock=clock)
    submit(fake_link, "bash", "-c", 'echo "plain $NPM_TOKEN / $NODE_OPTIONS"')
    run_until(worker, lambda: fake_link.of_type(MessageType.RESULT))
    log = fake_link.log_text()
    assert "fake-machine-value" not in log
    assert "plain [redacted] / --max-old-space-size=4096" in log
